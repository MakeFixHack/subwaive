import datetime
import icalendar
import os
from pathlib import Path
import pytz #!!! your sometimes adding local and sometimes adding utc, if they are tz-aware does it mater?
import requests

from django.db import models
from django.db.models import Q

from docuseal import docuseal

import stripe

from subwaive.settings import BASE_DIR

# https://www.docuseal.com/docs/api
DOCUSEAL_API_KEY = os.environ.get("DOCUSEAL_API_KEY")
DOCUSEAL_API_ENDPOINT = os.environ.get("DOCUSEAL_API_ENDPOINT")
DOCUSEAL_WWW_ENDPOINT = os.environ.get("DOCUSEAL_WWW_ENDPOINT")

docuseal.url = DOCUSEAL_API_ENDPOINT
docuseal.key = DOCUSEAL_API_KEY

# https://docs.stripe.com/api
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY")
STRIPE_WWW_ENDPOINT = os.environ.get("STRIPE_WWW_ENDPOINT")

stripe.api_key = STRIPE_API_KEY
#!!! overtime, the history being pulled from Stripe or Docuseal will get longer and longer
#!!! updating selectively using webhooks is more desirable than batch refreshes once the history gets long
#!!! manual way to refresh particular customers or products may be desirable

TIME_ZONE = os.environ.get("TIME_ZONE")
CALENDAR_URL = os.environ.get("CALENDAR_URL")
CALENDAR_ICS_PATH = BASE_DIR / "subwaive/static/ics/calendar.ics"

class DocusealField(models.Model):
    """ Fields titles flagged for  DocusealFieldStore """
    field = models.CharField(max_length=256)

    class Meta:
        ordering = ('field',)

    def __str__(self):
        return f"""{ self.field }"""


class DocusealFieldStore(models.Model):
    """ Fields that should be saved from DocusealSubmission """
    submission = models.ForeignKey("subwaive.DocusealSubmission", blank=True, null=True, on_delete=models.CASCADE, help_text="What is this person's preferred email address?")
    field = models.ForeignKey("subwaive.DocusealField", blank=True, null=True, on_delete=models.CASCADE, help_text="What is this person's preferred email address?")
    value = models.CharField(max_length=256)

    class Meta:
        ordering = ('field',)

    def __str__(self):
        return f"""{ self.field }"""
    
    def refresh():
        """ clear out existing records and repopulate them from the API """
        Log.objects.create(description="Refresh DocusealFieldStore")
        DocusealFieldStore.objects.all().delete()

        important_fields = DocusealField.objects.all()

        for submission in DocusealSubmission.objects.all():
            s = docuseal.get_submission(submission.submission_id)
            for field in important_fields:
                for form_field in s['submitters'][0]['values']:
                    if form_field['field'].lower().strip() == field.field.lower().strip():
                        if form_field['value']:
                            DocusealFieldStore.objects.create(submission=submission, field=field, value=form_field['value'])


class DocusealSubmission(models.Model):
    """ A Docuseal submission """
    submission_id = models.PositiveIntegerField()
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16)
    slug = models.CharField(max_length=32)
    template = models.ForeignKey("subwaive.DocusealTemplate", blank=True, null=True, on_delete=models.CASCADE, help_text="What is this person's preferred email address?")

    class Meta:
        ordering = ('-completed_at', 'status', 'slug',)

    def __str__(self):
        return f"""{ self.submission_id } / { self.template } / { self.slug } / { self.status } / {self.completed_at }"""

    def new(submission_id, slug, status, completed_at, template_id, submitters=None):
        """ Create a new instance """
        template = DocusealTemplate.objects.get(template_id=template_id)
        doc_sub = DocusealSubmission.objects.create(submission_id=submission_id, slug=slug, status=status, completed_at=completed_at, template=template)
        Log.objects.create(description="Create DocusealSubmission", json={'submission_id': submission_id})
        if submitters:
            DocusealSubmitterSubmission.objects.bulk_create([DocusealSubmitterSubmission(submission=doc_sub, submitter=DocusealSubmitter.objects.get(submitter_id=s['submitter_id']), status=s['status'], role=s['role']) for s in submitters])

    def refresh():
        """ clear out existing records and repopulate them from the API """
        Log.objects.create(description="Refresh DocusealSubmission")
        DocusealSubmission.objects.all().delete()
        last_submission_id = None
        pagination_next = True
        while pagination_next:
            api_dict = {'limit': 100}
            if last_submission_id:
                api_dict['after'] = last_submission_id
            
            submissions = docuseal.list_submissions(api_dict)
            
            last_submission_id = submissions['pagination']['next']
            if not last_submission_id:
                pagination_next = False

            for submission in submissions['data']:
                if submission['status'] == 'completed':
                    submitters = [{'submitter_id': s['id'], 'status': s['status'], 'role': s['role']} for s in submission['submitters']]
                    if DocusealTemplate.objects.filter(template_id=submission['template']['id']).exists():
                        DocusealSubmission.new(submission['id'], submission['slug'], submission['status'], submission['completed_at'], submission['template']['id'], submitters)

    def get_url(self):
        """ URL for a hyperlink """
        return f"{ DOCUSEAL_WWW_ENDPOINT }/submissions/{ self.submission_id }"


class DocusealSubmitter(models.Model):
    """ A Docuseal submitter - often per documents """
    submitter_id = models.PositiveIntegerField()
    email = models.EmailField()
    slug = models.CharField(max_length=32)

    class Meta:
        ordering = ('email', 'slug',)

    def __str__(self):
        return f"""{ self.submitter_id } / { self.email } / { self.slug }"""
    
    def _auto_associate(self):
        """ automatically associate this submitter with the first person 
        it finds that shares this email address. if none is found create a Person for it. """
        if not PersonDocuseal.objects.filter(submitter__id=self.submitter_id):
            person = None
            email = PersonEmail.objects.filter(email=self.email).first()
            if email:
                person = email.person
            if person:
                PersonDocuseal.objects.create(person=person, submitter=self)
            else:
                person = Person.objects.create(name=self.email)
                email = PersonEmail.objects.create(person=person, email=self.email)
                person.preferred_email = email
                person.save()

    def new(submitter_id, email, slug):
        """ Create a new instance and auto_associate """
        doc_sub = DocusealSubmitter.objects.create(submitter_id=submitter_id, email=email, slug=slug)
        Log.objects.create(description="Create DocusealSubmitter", json={'submitter_id': submitter_id})
        doc_sub._auto_associate()

    def search(email):
        """ search for a Docuseal submitter from the API """
        submitter_id_list = []

        last_submitter_id = None
        pagination_next = True
        while pagination_next:
            api_dict = {'limit': 100, 'q': email}
            if last_submitter_id:
                api_dict['after'] = last_submitter_id
            
            submitters = docuseal.list_submitters(api_dict)
            
            last_submitter_id = submitters['pagination']['next']
            if not last_submitter_id:
                pagination_next = False

            for submitter in submitters['data']:
                submitter_id_list.append({'submitter_id': submitter['id'], 'email': submitter['email']})
        
        return submitter_id_list

    def refresh():
        """ clear out existing records and repopulate them from the API """
        Log.objects.create(description="Refresh DocusealSubmitter")
        DocusealSubmitter.objects.all().delete()
        last_submitter_id = None
        pagination_next = True
        while pagination_next:
            api_dict = {'limit': 100}
            if last_submitter_id:
                api_dict['after'] = last_submitter_id
            
            submitters = docuseal.list_submitters(api_dict)
            
            last_submitter_id = submitters['pagination']['next']
            if not last_submitter_id:
                pagination_next = False

            for submitter in submitters['data']:
                DocusealSubmitter.new(submitter['id'], submitter['email'], submitter['slug'])


class DocusealSubmitterSubmission(models.Model):
    """ A map between Docuseal submitter and  submission """
    submitter = models.ForeignKey("subwaive.DocusealSubmitter", blank=True, null=True, on_delete=models.CASCADE, help_text="What is this person's preferred email address?")
    submission = models.ForeignKey("subwaive.DocusealSubmission", blank=True, null=True, on_delete=models.CASCADE, help_text="What is this person's preferred email address?")
    status = models.CharField(max_length=32)
    role = models.CharField(max_length=64)

    class Meta:
        ordering = ('-status', 'role',)

    def __str__(self):
        return f"""{ self.submitter } / { self.submission } / {self.role }"""
    

class DocusealTemplate(models.Model):
    """ A Docuseal template """
    template_id = models.PositiveIntegerField()
    folder_name = models.CharField(max_length=128)
    name = models.CharField(max_length=128)
    slug = models.CharField(max_length=32)

    class Meta:
        ordering = ('folder_name', 'name', 'slug',)

    def __str__(self):
        return f"""{ self.template_id } / { self.folder_name } / { self.name } / { self.slug }"""

    def new(template_id, folder_name, name, slug):
        """ Create a new instance and auto_associate """
        DocusealTemplate.objects.create(template_id=template_id, folder_name=folder_name, name=name, slug=slug)
        Log.objects.create(description="Create DocusealTemplate", json={'template_id': template_id})

    def refresh():
        """ clear out existing records and repopulate them from the API """
        Log.objects.create(description="Refresh DocusealTemplate")
        DocusealTemplate.objects.all().delete()
        last_template_id = None
        pagination_next = True
        while pagination_next:
            api_dict = {'limit': 100}
            if last_template_id:
                api_dict['after'] = last_template_id
            
            templates = docuseal.list_templates(api_dict)
            
            last_template_id = templates['pagination']['next']
            if not last_template_id:
                pagination_next = False

            for template in templates['data']:
                if not template['archived_at']:
                    DocusealTemplate.new(template['id'], template['folder_name'], template['name'], template['slug'])

    def get_url(self):
        """ URL for a hyperlink """
        return f"{ DOCUSEAL_WWW_ENDPOINT }/d/{ self.slug }"
    

class Event(models.Model):
    """ An event from an ical file """
    UID = models.UUIDField()
    summary = models.CharField(max_length=512, help_text='What is the event summary?')
    description = models.TextField(max_length=2048, help_text='What is the event description?')
    start = models.DateTimeField(help_text='When does the event begin?')
    end = models.DateTimeField(help_text='When does the event finish?')

    class Meta:
        ordering = ('-start', 'summary',)

    def __str__(self):
        return f"""{ self.summary[:50] } / { self.start } / { self.end }"""
    
    def download_ics():
        """ download from our calendar URL """
        local_path = CALENDAR_ICS_PATH
        response = requests.get(CALENDAR_URL, stream=True)
        response.raise_for_status()

        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                            
    def get_current_event():
        """ return any Event objects for events that are currently happening """
        return Event.objects.filter(start__lte=datetime.datetime.now(), end__gte=datetime.datetime.now())

    def refresh():
        """ Refresh events from ical file """
        ics_path = Path(CALENDAR_ICS_PATH)
        calendar = icalendar.Calendar.from_ical(ics_path.read_bytes())

        for event in calendar.events:
            uid = event.get("UID")
            summary = event.get("SUMMARY").__str__()
            description = event.get("DESCRIPTION").__str__()[:2048]
            start = event.start
            end = event.end
            
            event_qs = Event.objects.filter(UID=uid)
            if event_qs.exists():
                event = event_qs.first()
                is_updated = False
                if event.summary != summary:
                    is_updated = True
                    event.summary = summary
                if event.description != description:
                    is_updated = True
                    event.description = description
                if event.start != start:
                    is_updated = True
                    event.start = start
                if event.end != end:
                    is_updated = True
                    event.end = end
                if is_updated:
                    event.save()
                Log.objects.create(description="Update Event", json={'uid': uid})

            else:
                event = Event.objects.create(UID=uid, summary=summary, description=description, start=start, end=end)
                Log.objects.create(description="Create Event", json={'uid': event.UID})
        Log.objects.create(description="Refresh Event")


class Log(models.Model):
    """ Log activities """
    timestamp = models.DateTimeField(auto_now_add=True, help_text='When was the event logged?')
    description = models.CharField(max_length=512, help_text='What happened?')
    other_info = models.TextField(max_length=4096, blank=True, null=True, help_text='Additional detail')
    json = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ('-timestamp',)

    def __str__(self):
        return f"""{ self.timestamp } / { self.description[:32] }"""
    
    def date(self, tz=TIME_ZONE):
        """ returns the date for the requested tz """
        return self.timestamp.astimezone(pytz.timezone(tz)).date()
        
    def get_last(description, other_info=None, json=None):
        """ return the last log entry with a description """
        filter_condition = Q()
        filter_condition.add(Q(description=description), Q.AND)

        if other_info:
            filter_condition.add(Q(other_info__icontains=other_info), Q.AND)
        
        if json:
            for key,val in json.items():
                filter_condition.add(Q(**{f'json__{key}': val}), Q.AND)

        return Log.objects.filter(filter_condition).order_by('-timestamp').first()

class Permission(models.Model):
    """ Permissions defining what data users can access """  
    class Meta:
        permissions = [
            ("can_view_detail", "Can view detailed user data"),
            ("can_view_status", "Can tell if user is current"),
            ("can_search_people", "Can search for people"),
            ("can_list_people", "Can view people list"),
            ("can_remove_check_in", "Can delete a check-in record"),
            ("can_refresh_data", "Can force Docuseal and Stripe data to refresh"),
        ]    

class Person(models.Model):
    """ A dummy model for linking records together """
    name = models.CharField(max_length=128, help_text="What is the preferred nae for ths person?")
    preferred_email = models.ForeignKey("subwaive.PersonEmail", related_name="+", blank=True, null=True, on_delete=models.CASCADE, help_text="What is this person's preferred email address?")

    class Meta:
        ordering = ('name', 'preferred_email__email',)

    def __str__(self):
        return f"""{ self.name } / { self.preferred_email }"""
    
    def check_in(self, event_id):
        """ check the person into an event """
        event = Event.objects.get(id=event_id)
        return PersonEvent.objects.create(person=self, event=event)

    def check_membership_status(self):
        """ return true if they have a current membership """
        has_membership = False
        if self.get_memberships():
            has_membership = True

        return has_membership 
        
    def get_last_check_in(self):
        """ return the last check-in for a person """
        return PersonEvent.objects.filter(person=self).order_by('-event__end').first()

    def get_submissions(self):
        """ fetch links to each document the person has signed """
        submitters = PersonDocuseal.objects.filter(person=self).values_list('submitter')
        dss = DocusealSubmitterSubmission.objects.filter(submitter__in=submitters).values_list('submission__id')
        submissions = DocusealSubmission.objects.filter(id__in=dss).order_by('template__folder_name')

        return submissions
        
    def get_documents(self):
        """ fetch links to each document the person has signed """
        submissions = self.get_submissions()
        
        documents = [
            {
                'folder_name': doc.template.folder_name,
                'template_name': doc.template.name,
                'status': doc.status,
                'completed_at': doc.completed_at,
                'url': doc.get_url(),
                'important_fields': [{'field': f.field, 'value': f.value} for f in DocusealFieldStore.objects.filter(submission=doc)]
            }
            for doc in submissions
        ]

        return documents

    def get_day_passes(self):
        """ fetch a list of day-passes purchased """
        return self.get_onetime_payments("pay-what-you")

    def get_donor_status(self):
        """ give a categorical description of how much they've donated """
        otp = self.get_onetime_payments("donation")
        
        donor_status = []
        if self.get_subscriptions("donation"):
            donor_status.append("Makes a recurring donation")
        if otp:
            if len(otp) == 1:
                donor_status.append(f"Made a one-time donation")
            else:
                donor_status.append(f"Made { len(otp) } one-time donations")

        return donor_status

    def get_email_list(self):
        """ return a list of emails associated with this person """
        return PersonEmail.objects.filter(person=self)

    def get_events(self):
        """ fetch a list of events purchased """
        return self.get_onetime_payments("event")

    def get_memberships(self):
        """ fetch a list of memberships """
        return self.get_subscriptions("membership")

    def get_onetime_payments(self, product_description):
        """ fetch data on each one-time purchase the person has made """
        emails = [e.email for e in PersonEmail.objects.filter(person=self)]
        payment_links = StripePaymentLinkPrice.objects.filter(price__product__name__icontains=product_description)
        
        otp = []
        for payment_link in payment_links:
            charges = stripe.checkout.Session.list(payment_link=payment_link.payment_link)
            for charge in charges:
                if charge:
                    if charge.customer_details:
                        if charge.customer_details.email in emails:
                            product = stripe.checkout.Session.list_line_items(charge.id).data[0]
                            otp.append(
                                {
                                    'description': product.description, 
                                    'date': datetime.datetime.fromtimestamp(charge.created, tz=pytz.timezone(TIME_ZONE)).date(),
                                    'url': f'{ STRIPE_WWW_ENDPOINT }/payments/{ charge.payment_intent }',
                                    }
                                )

        return otp
    
    def get_subscriptions(self, description):
        """ fetch data to each subscription the person has purchased """
        customers = PersonStripe.objects.filter(person=self).values_list('customer')
        stripe_customers = StripeCustomer.objects.filter(id__in=customers)
        products = StripeProduct.objects.filter(Q(name__icontains=description)|Q(description__icontains=description))
        subscription_item = StripeSubscriptionItem.objects.filter(subscription__customer__in=stripe_customers, price__product__in=products).order_by('subscription__name')

        subscriptions = [
                    {
                        'description': item.price.product.description, 
                        'status': item.subscription.status, 
                        'current_period_end': item.subscription.current_period_end,
                        'name': item.subscription.name,
                        'url': item.subscription.get_url(),
                        }
                        for item in subscription_item
                    ]
        return subscriptions

    def merge(self, merge_child_id):
        """ Merge the associations from merge_child into self and delete merge_child """
        merge_child = Person.objects.get(id=merge_child_id)

        Log.objects.create(description="Merge Person", json={'person_id': self.id, 'merge_child_id': merge_child_id})
        pds = PersonDocuseal.objects.filter(person=merge_child)
        for pd in pds:
            pd.person = self
            pd.save()

        pes = PersonEmail.objects.filter(person=merge_child)
        for pe in pes:
            pe.person = self
            pe.save()

        pss = PersonStripe.objects.filter(person=merge_child)
        for ps in pss:
            ps.person = self
            ps.save()

        merge_child.delete()

    def search(search_term):
        """ search for a Person """
        person_id_list = set([pe.person.id for pe in PersonEmail.objects.filter(Q(person__name__icontains=search_term)|Q(email__icontains=search_term))])

        return Person.objects.filter(id__in=person_id_list)


class PersonDocuseal(models.Model):
    """ A map between Person and DocusealSubmitter """
    person = models.ForeignKey("subwaive.Person", on_delete=models.CASCADE, help_text="Who is the person associated with this Docuseal submitter?")
    submitter = models.ForeignKey("subwaive.DocusealSubmitter", on_delete=models.CASCADE, help_text="What is the Docuseal submitter id associated with this person?")

    class Meta:
        ordering = ('person', 'submitter',)

    def __str__(self):
        return f"""{ self.person } / { self.submitter }"""
    

class PersonEmail(models.Model):
    """ A list of email addresses associated with a Person """
    person = models.ForeignKey("subwaive.Person", on_delete=models.CASCADE, help_text="Who is the person associated with this Docuseal submitter?")
    email = models.EmailField(help_text="What is this person's email address?")

    class Meta:
        ordering = ('person', 'email',)

    def __str__(self):
        return f"""{ self.person.name } / { self.email }"""

    def unmerge(self):
        """ Break linkages between self and an email address (including Stripe and Docuseal accounts)"""
        print('unmerge')
        email = self.email
        print("pre-delete",email)
        person_id = self.person.id
        print(person_id)

        Log.objects.create(description="Unmerge Person", json={'person_id': person_id, 'email': email})

        PersonStripe.objects.filter(person__id=person_id).delete()
        PersonDocuseal.objects.filter(person__id=person_id).delete()
        self.delete()
        print("post-delete",email)

        for ds in DocusealSubmitter.objects.filter(email=email):
            print(ds)
            ds._auto_associate()

        for sc in StripeCustomer.objects.filter(email=email):
            print(sc)
            sc._auto_associate()


class PersonEvent(models.Model):
    """ A map between Person and Event """
    person = models.ForeignKey("subwaive.Person", on_delete=models.CASCADE, help_text="Who is the person associated with this Docuseal submitter?")
    event = models.ForeignKey("subwaive.Event", on_delete=models.CASCADE, help_text="Who is the person associated with this Docuseal submitter?")

    class Meta:
        ordering = ('person', 'event',)

    def __str__(self):
        return f"""{ self.person } / { self.event }"""


class PersonStripe(models.Model):
    """ A map between Person and StripeCustomer """
    person = models.ForeignKey("subwaive.Person", on_delete=models.CASCADE, help_text="Who is the person associated with this Stipe customer?")
    customer = models.ForeignKey("subwaive.StripeCustomer", on_delete=models.CASCADE, help_text="What is the Stripe customer id associated with this person?")

    class Meta:
        ordering = ('person', 'customer',)

    def __str__(self):
        return f"""{ self.person } / { self.customer.stripe_id }"""
    

class QRCategory(models.Model):
    """ Categories for organizing QR codes """
    name = models.CharField(max_length=64, help_text="What is the name of the View?")
    is_sensitive = models.BooleanField(default=False)

    class Meta:
        ordering = ('is_sensitive', 'name',)

    def __str__(self):
        sensitivity_label = "PUBLIC"
        if self.is_sensitive:
            sensitivity_label = "SENSITIVE"
        return f"""{ sensitivity_label } / { self.name }"""


class QRCustom(models.Model):
    """ User-defined QR codes """
    name = models.CharField(max_length=64, help_text="What is the name of the View?")
    category = models.ForeignKey("subwaive.QRCategory", on_delete=models.CASCADE, help_text="What category does this QR code belong to?")
    content = models.CharField(max_length=4096, help_text="What is the QR code's payload?")

    class Meta:
        ordering = ('category__name', 'name',)

    def __str__(self):
        return f"""{ self.category.name } / { self.name }"""


class StripeCustomer(models.Model):
    """ A Stripe Customer """
    stripe_id = models.CharField(max_length=64)
    name = models.CharField(max_length=128)
    email = models.EmailField()

    class Meta:
        ordering = ('email', 'name',)

    def __str__(self):
        return f"""{ self.stripe_id } / { self.name } / { self.email }"""

    def _auto_associate(self):
        """ automatically associate this customer with the first person 
        it finds that shares this email address. if none is found create a Person for it. """
        if not PersonStripe.objects.filter(customer=self):
            person = None
            email = PersonEmail.objects.filter(email=self.email).first()
            if email:
                person = email.person
            if person:
                PersonStripe.objects.create(person=person, customer=self)
            else:
                person = Person.objects.create(name=self.email)
                email = PersonEmail.objects.create(person=person, email=self.email)
                person.preferred_email = email
                person.save()

    def create_and_or_return(stripe_id):
        """ return a record if it exists, else create and return it """
        json = {'stripe_id': stripe_id}

        customer_qs = StripeCustomer.objects.filter(stripe_id=stripe_id)
        if customer_qs.exists():
            customer = customer_qs.first()
        else:
            api_record = stripe.Customer.retrieve(stripe_id)
            customer = StripeCustomer.objects.create(stripe_id=stripe_id, name=api_record.name, email=api_record.email)
            Log.objects.create(description="Create StripeCustomer", json=json)

        return customer

    def create_or_update(stripe_id):
        """ updates an existing record, otherwise creates one """
        json = {'stripe_id': stripe_id}

        customer_qs = StripeCustomer.objects.filter(stripe_id=stripe_id)
        api_record = stripe.Customer.retrieve(stripe_id)

        if customer_qs.exists():
            customer = customer_qs.first()
            customer.name = api_record.name
            customer.email = api_record.email
            customer.save()
            Log.objects.create(description="Update StripeCustomer", json=json)
        else:
            StripeCustomer.objects.create(stripe_id=stripe_id, name=api_record.name, email=api_record.email)
            Log.objects.create(description="Create StripeCustomer", json=json)


    def get_url(self):
        """ URL for a hyperlink """
        return f"{ STRIPE_WWW_ENDPOINT }/customers/{ self.stripe_id }"

    def new(stripe_id, name, email):
        sc = StripeCustomer.objects.create(stripe_id=stripe_id, name=name, email=email)
        Log.objects.create(description="Create StripeCustomer", json={'stripe_id': stripe_id})
        sc._auto_associate()

    def search(name, email):
        """ search for a Stripe customer from the API """
        pass

    def refresh():
        """ clear out existing records and repopulate them from the API """
        Log.objects.create(description="Refresh StripeCustomer")
        StripeCustomer.objects.all().delete()
        for customer in stripe.Customer.list().auto_paging_iter():
            stripe_id = customer['id']
            name = customer['name'][:128]
            email = customer['email'][:128]
            StripeCustomer.new(stripe_id=stripe_id, name=name, email=email)


# class StripeOneTimePayment(models.Model):
#     """ A Stripe Subscription """
#     stripe_id = models.CharField(max_length=64)
#     customer = models.ForeignKey("subwaive.StripeCustomer", on_delete=models.CASCADE, help_text="What Stripe Customer holds this Subscription?")
#     date = models.DateTimeField(null=True, blank=True)
#     status = models.CharField(max_length=64)
#     name = models.CharField(max_length=128)
#     product = models.ForeignKey("subwaive.StripeProduct", on_delete=models.CASCADE, help_text="What Stripe Customer holds this Subscription?")

#     class Meta:
#         ordering = ('stripe_id',)

#     def __str__(self):
#         return f"""{ self.stripe_id } / { self.product } / { self.date }"""

#     def get_url(self):
#         """ URL for a hyperlink """
#         return f"{ STRIPE_WWW_ENDPOINT }/payments/{ self.stripe_id }"

#     def refresh():
#         """ clear out existing records and repopulate them from the API """
#         Log.objects.create(description="Refresh StripeSubscription")
#         StripeOneTimePayment.objects.all().delete()
#         for pl in StripePaymentLink.objects.filter(interval='one-time'):
#             for cs in stripe.checkout.Session.list(payment_link=pl.stripe_id):
#                 # link customer_details.email and pl.price.product and date and status
#                 # that will let us know who bought which product from which link, when, and if it succeeded
#                 pass

class StripePaymentLink(models.Model):
    """ A Stripe PaymentLink """
    stripe_id = models.CharField(max_length=64)
    url = models.URLField()
    # metadata to get name for day-pass event?

    class Meta:
        ordering = ('stripe_id',)

    def __str__(self):
        return f"""{ self.stripe_id } / { self.url }"""

    def create_or_update(stripe_id):
        """ updates an existing record, otherwise creates one """
        json = {'stripe_id': stripe_id}

        payment_link_qs = StripePaymentLink.objects.filter(stripe_id=stripe_id)
        if payment_link_qs.exists():
            payment_link = payment_link_qs
            payment_link.create_or_update_children()
        else:
            plink = StripePaymentLink.objects.create(stripe_id=payment_link.id, url=payment_link.url)
            Log.objects.create(description="Create StripePaymentLink", json=json)
            plink.create_or_update_children()

    def create_or_update_children(self):
        """ updates existing child records, otherwise creates them """
        for line_item in stripe.PaymentLink.list_line_items(self.stripe_id).auto_paging_iter():
            price = StripePrice.create_or_update(line_item.price.id)
            StripePaymentLinkPrice.create_if_needed(payment_link=self, price=price)

    def get_url(self):
        """ URL for a hyperlink """
        return f"{ STRIPE_WWW_ENDPOINT }/payment-links/{ self.stripe_id }"

    def refresh():
        """ clear out existing records and repopulate them from the API """
        Log.objects.create(description="Refresh StripePaymentLink")
        StripePaymentLink.objects.all().delete()
        for payment_link in stripe.PaymentLink.list(active=True).auto_paging_iter():
            StripePaymentLink.objects.create(stripe_id=payment_link.id, url=payment_link.url)
            Log.objects.create(description="Create StripePaymentLink", json={'stripe_id': payment_link.id})



class StripePaymentLinkPrice(models.Model):
    """ A map between Stripe PaymentLink and Price """
    payment_link = models.ForeignKey("subwaive.StripePaymentLink", on_delete=models.CASCADE, help_text="What Stripe Payment Link is being mapped?")
    price = models.ForeignKey("subwaive.StripePrice", on_delete=models.CASCADE, help_text="What Stripe Price is being mapped?")

    class Meta:
        ordering = ('price', 'payment_link',)

    def __str__(self):
        return f"""{ self.price } / { self.payment_link }"""

    def create_if_needed(payment_link, price):
        """ create a PaymentLink-Price map if one does not already exist """
        if not StripePaymentLinkPrice.objects.filter(payment_link=payment_link, price=price).exists():
            StripePaymentLinkPrice.objects.create(payment_link=payment_link, price=price)
            Log.objects.create(description="Create StripePaymentLinkPrice")
    
    def refresh():
        Log.objects.create(description="Refresh StripePaymentLinkPrice")
        StripePaymentLinkPrice.objects.all().delete()
        for payment_link in StripePaymentLink.objects.all():
            for line_item in stripe.PaymentLink.list_line_items(payment_link.stripe_id).auto_paging_iter():
                stripe_id = line_item.price.id
                price = StripePrice.objects.get(stripe_id=stripe_id)
                StripePaymentLinkPrice.objects.create(payment_link=payment_link, price=price)


class StripePrice(models.Model):
    """ A Stripe Price """
    stripe_id = models.CharField(max_length=64)
    name = models.CharField(max_length=64, help_text="What is the name of the Price?")
    interval = models.CharField(max_length=64)
    price = models.IntegerField()
    product = models.ForeignKey("subwaive.StripeProduct", on_delete=models.CASCADE, help_text="What Stripe Product does this Price apply to?")

    class Meta:
        ordering = ('name', 'interval', 'price',)

    def __str__(self):
        description = f"""{ self.name } ({ self.interval }): """
        if self.price:
            price = "$"+"{:.2f}".format(float(self.price)/100)
        else:
            price = "name-your-own-price"
        
        return f"{ description } { price }"

    def create_and_or_return(stripe_id):
        """ create a StripePrice if one does not already exist """
        json = {'stripe_id': stripe_id}

        price_qs = StripePrice.objects.filter(stripe_id=stripe_id)
        if not price_qs.exists():
            api_prc = stripe.Price.retrieve(stripe_id)
            product = StripeProduct.create_or_update(api_prc.product)
            price = StripePrice.objects.create(stripe_id=stripe_id, product=product, name=api_prc['name'], interval=api_prc['interval'], price=api_prc['price_amount'])
            Log.objects.create(description="Create StripePrice", json=json)
        else:
            price = price_qs.first()
        
        return price

    def create_or_update(stripe_id):
        """ updates an existing record, otherwise creates one """
        json = {'stripe_id': stripe_id}

        price_qs = StripePrice.objects.filter(stripe_id=stripe_id)
        api_record = StripePrice.fetch_api_data(stripe_id)
        api_prc = StripePrice.dict_from_api(api_record)
        product = StripeProduct.create_or_update(api_prc.product)

        if price_qs.exists():
            price = price_qs.first()
            price.name = api_prc['name']
            price.interval = api_prc['interval']
            price.price = api_prc['price_amount']
            price.product = product
            price.save()
            Log.objects.create(description="Update StripePrice", json=json)
        else:
            StripePrice.objects.create(stripe_id=stripe_id, product=product, name=api_prc['name'], interval=api_prc['interval'], price=api_prc['price_amount'])
            Log.objects.create(description="Create StripePrice", json=json)

    def fetch_api_data(stripe_id):
        """ fetch api data """
        return stripe.Price.retrieve(stripe_id)
    
    def dict_from_api(api_record):
        """ returns a dict of required values from an API record """
        stripe_id = api_record.id
        interval = 'one-time'
        if 'recurring' in api_record.keys():
            if api_record.recurring:
                interval = api_record.recurring.interval
        name = api_record.id
        if api_record.nickname:
            name = api_record.nickname
        price_amount = 0
        if api_record.unit_amount:
            price_amount = api_record.unit_amount
        
        return {'stripe_id': stripe_id, 'interval': interval, 'name': name, 'price_amount': price_amount, }

    def get_url(self):
        """ URL for a hyperlink """
        return f"{ STRIPE_WWW_ENDPOINT }/prices/{ self.stripe_id }"

    def refresh():
        """ clear out existing records and repopulate them from the API """
        Log.objects.create(description="Refresh StripePrice")
        StripePrice.objects.all().delete()
        for price in stripe.Price.list(active=True).auto_paging_iter():
            print(price.product)
            if stripe.Product.retrieve(price.product).active:
                product = StripeProduct.objects.get(stripe_id=price.product)
                api_prc = StripePrice.dict_from_api(price)
                StripePrice.objects.create(stripe_id=api_prc['stripe_id'], product=product, name=api_prc['name'], interval=api_prc['interval'], price=api_prc['price_amount'])
                Log.objects.create(description="Create StripePrice", json={'stripe_id': api_prc['stripe_id']})


class StripeProduct(models.Model):
    """ A Stripe Product """
    stripe_id = models.CharField(max_length=64)
    name = models.CharField(max_length=64)
    description = models.TextField(max_length=512)

    class Meta:
        ordering = ('name', 'description',)

    def __str__(self):
        return f"""{ self.stripe_id } / { self.name } / { self.description[:50] }"""

    def create_and_or_return(stripe_id):
        """ create a StripeProduct if one does not already exist """
        json = {'stripe_id': stripe_id}

        product_qs = StripeProduct.objects.filter(stripe_id=stripe_id)
        if not product_qs.exists():
            api_prd = stripe.Product.retrieve(stripe_id)
            product = StripeProduct.objects.create(stripe_id=stripe_id, name=api_prd.name, description=api_prd.description)
            Log.objects.create(description="Create StripeProduct", json=json)
        else:
            product = product_qs.first()
        
        return product

    def create_or_update(stripe_id):
        """ updates an existing record, otherwise creates one """
        json = {'stripe_id': stripe_id}
        
        product_qs = StripeProduct.objects.filter(stripe_id=stripe_id).first()
        api_prd = stripe.Product.retrieve(stripe_id)
        if product_qs.exists():
            product = product_qs
            product.name = api_prd.name
            product.description = api_prd.description
            product.save()
            Log.objects.create(description="Update StripeProduct", json=json)
        else:
            StripeProduct.objects.create(stripe_id=stripe_id, name=api_prd.name, description=api_prd.description)
            Log.objects.create(description="Create StripeProduct", json=json)

    def get_url(self):
        """ URL for a hyperlink """
        return f"{ STRIPE_WWW_ENDPOINT }/products/{ self.stripe_id }"

    def refresh():
        """ clear out existing records and repopulate them from the API """
        Log.objects.create(description="Refresh StripeProduct")
        StripeProduct.objects.all().delete()
        for product in stripe.Product.list(active=True).auto_paging_iter():
            StripeProduct.objects.create(stripe_id=product.id, name=product.name, description=product.description)
            Log.objects.create(description="Create StripeProduct", json={'stripe_id': product.id})


class StripeSubscription(models.Model):
    """ A Stripe Subscription """
    stripe_id = models.CharField(max_length=64)
    customer = models.ForeignKey("subwaive.StripeCustomer", on_delete=models.CASCADE, help_text="What Stripe Customer holds this Subscription?")
    created = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=64)
    name = models.CharField(max_length=128)

    # class Meta:
    #     ordering = ('category', 'name',)

    def __str__(self):
        return f"""{ self.stripe_id } / { self.status } / { self.current_period_end }"""

    def create_or_update(stripe_id):
        """ updates an existing record, otherwise creates one """
        json = {'stripe_id': stripe_id}

        subscription_qs = StripeSubscription.objects.filter(stripe_id=stripe_id)
        api_record = stripe.Subscription.retrieve(stripe_id)

        customer_id = api_record.customer
        created = StripeSubscription.transform_timestamp(api_record.created)
        current_period_end = StripeSubscription.transform_timestamp(api_record.current_period_end)
        status = api_record.status
        name = StripeSubscription.get_api_name(stripe_id)

        if subscription_qs.exists():
            if status == 'canceled':
                subscription_qs.delete()
                Log.objects.create(description="Cancel StripeSubscription", json=json)
            else:
                subscription = subscription_qs.first()
                subscription.customer = StripeCustomer.create_and_or_return(customer_id)
                subscription.created = created
                subscription.current_period_end = current_period_end
                subscription.status = status
                subscription.name = name
                subscription.save()
    
                Log.objects.create(description="Delete StripeSubscriptionItem", json={'subscription.id': subscription.id})
                StripeSubscriptionItem.objects.filter(subscription=subscription).delete()
                StripeSubscriptionItem.create_if_needed(api_record)
                Log.objects.create(description="Update StripeSubscription", json=json)
        elif status != 'canceled':
            customer = StripeCustomer.create_and_or_return(customer_id)
            subscription = StripeSubscription.objects.create(stripe_id=stripe_id, customer=customer, name=name, created=created, current_period_end=current_period_end, status=status)
            Log.objects.create(description="Delete StripeSubscriptionItem", json={'subscription.id': subscription.id})
            StripeSubscriptionItem.objects.filter(subscription=subscription).delete()
            StripeSubscriptionItem.create_if_needed(api_record)
            Log.objects.create(description="Create StripeSubscription", json=json)

    def transform_timestamp(timestamp):
        """ transforms a timestamp to a datetime """
        return datetime.datetime.fromtimestamp(timestamp, tz=pytz.timezone(TIME_ZONE))

    def get_api_name(stripe_id):
        """ return a name if provided in the checkout, else "self" """
        name = None

        session = stripe.checkout.Session.list(subscription=stripe_id)
        try:
            name = session.data[0].custom_fields[0].text.value
        except:
            pass
        if not name:
            name = "self"
        return name

    def get_url(self):
        """ URL for a hyperlink """
        return f"{ STRIPE_WWW_ENDPOINT }/subscriptions/{ self.stripe_id }"

    def refresh():
        """ clear out existing records and repopulate them from the API """
        Log.objects.create(description="Refresh StripeSubscription")
        StripeSubscription.objects.all().delete()
        for subscription in stripe.Subscription.search(query='-status:"canceled"').auto_paging_iter():
            customer = StripeCustomer.objects.get(stripe_id=subscription.customer)

            stripe_id = subscription['id']
            name = StripeSubscription.get_api_name(stripe_id)

            created = StripeSubscription.transform_timestamp(subscription.created)
            current_period_end = StripeSubscription.transform_timestamp(subscription.current_period_end)
            status = subscription.status

            StripeSubscription.objects.create(stripe_id=stripe_id, customer=customer, name=name, created=created, current_period_end=current_period_end, status=status)
            StripeSubscriptionItem.create_if_needed(subscription)
            Log.objects.create(description="Create StripeSubscription", json={'stripe_id': stripe_id})

class StripeSubscriptionItem(models.Model):
    """ A Stripe SubscriptionItem """
    stripe_id = models.CharField(max_length=64)
    subscription = models.ForeignKey("subwaive.StripeSubscription", on_delete=models.CASCADE, help_text="What Stripe Price is being mapped?")
    price = models.ForeignKey("subwaive.StripePrice", on_delete=models.CASCADE, help_text="What Stripe Price is being mapped?")

    class Meta:
        ordering = ('stripe_id', 'price',)

    def __str__(self):
        return f"""{ self.stripe_id } / { self.subscription } / { self.price }"""

    def create_if_needed(api_sub):
        """ loops through a Stripe API Subscription object and creates a SubscriptionItem if one does not already exist """
        for item in api_sub['items']:
            item_id = item.id
            price_id = item.price.id
            price = StripePrice.create_and_or_return(stripe_id=price_id)
            subscription = StripeSubscription.objects.get(stripe_id=api_sub.id)
            if not StripeSubscriptionItem.objects.filter(stripe_id=item_id, subscription=subscription, price=price).exists():
                StripeSubscriptionItem.objects.create(stripe_id=item_id, subscription=subscription, price=price)
                Log.objects.create(description="Create StripeSubscriptionItem")

