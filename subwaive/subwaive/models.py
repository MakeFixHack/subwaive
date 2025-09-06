import datetime
import logging
import os
import pytz #!!! your sometimes adding local and sometimes adding utc, if they are tz-aware does it mater?
import caldav

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

TIME_ZONE = os.environ.get("TIME_ZONE")
CALENDAR_URL = os.environ.get("CALENDAR_URL")

LOGGING_LEVEL = int(os.environ.get("LOGGING_LEVEL", logging.DEBUG))

def fromtimestamp(timestamp):
    """ transforms a timestamp to a datetime """
    return datetime.datetime.fromtimestamp(timestamp, tz=pytz.timezone(TIME_ZONE))


class DocusealField(models.Model):
    """ Fields titles flagged for  DocusealFieldStore """
    field = models.CharField(max_length=256)

    class Meta:
        ordering = ('field',)

    def __str__(self):
        return f"""{ self.field }"""


class DocusealFieldStore(models.Model):
    """ Fields that should be saved from DocusealSubmission """
    submission = models.ForeignKey("subwaive.DocusealSubmission", blank=True, null=True, on_delete=models.CASCADE, help_text="Which submission is being extracted from?")
    field = models.ForeignKey("subwaive.DocusealField", blank=True, null=True, on_delete=models.CASCADE, help_text="What is the name of the field being extracted?")
    value = models.CharField(max_length=256)

    class Meta:
        ordering = ('field',)

    def __str__(self):
        return f"""{ self.field }"""

    def re_extract(submission_id):
        """ re-extract field store values for a DocusealSubmission """
        Log.new(logging_level=logging.INFO, description="Refresh DocusealFieldStore", json={'submission_id': submission_id})
        submission = DocusealSubmission.objects.get(submission_id=submission_id)
        DocusealFieldStore.objects.filter(submission=submission).delete()
        important_fields = DocusealField.objects.all()

        s = docuseal.get_submission(submission_id)
        for field in important_fields:
            for form_field in s['submitters'][0]['values']:
                if form_field['field'].lower().strip() == field.field.lower().strip():
                    if form_field['value']:
                        DocusealFieldStore.objects.create(submission=submission, field=field, value=form_field['value'])
                        if 'name' in field.field.lower():
                            submission._auto_name(form_field['value'])

    def refresh(max_existing_submission_id=None):
        """ clear out existing records and repopulate them from the API """
        if max_existing_submission_id:
            submissions = DocusealSubmission.objects.filter(submission_id__gt=max_existing_submission_id)
        else:
            submissions = DocusealSubmission.objects.all()
            Log.new(logging_level=logging.INFO, description="Refresh DocusealFieldStore")
            DocusealFieldStore.objects.all().delete()

        important_fields = DocusealField.objects.all()

        for submission in submissions:
            s = docuseal.get_submission(submission.submission_id)
            for field in important_fields:
                for form_field in s['submitters'][0]['values']:
                    if form_field['field'].lower().strip() == field.field.lower().strip():
                        if form_field['value']:
                            DocusealFieldStore.objects.create(submission=submission, field=field, value=form_field['value'])
                            if 'name' in field.field.lower():
                                submission._auto_name(form_field['value'])


class DocusealSubmission(models.Model):
    """ A Docuseal submission """
    submission_id = models.PositiveIntegerField(help_text="What is the Docuseal ID of this submission?")
    created_at = models.DateTimeField(null=True, blank=True, help_text="When was this submission created in Docuseal?")
    completed_at = models.DateTimeField(null=True, blank=True, help_text="When was this submission completed in Docuseal?")
    archived_at = models.DateTimeField(null=True, blank=True, help_text="When was this submission archived in Docuseal?")
    status = models.CharField(max_length=16, help_text="What is the Docuseal status of this submission?")
    slug = models.CharField(max_length=32, help_text="What is the URL slug for this submission?")
    template = models.ForeignKey("subwaive.DocusealTemplate", blank=True, null=True, on_delete=models.CASCADE, help_text="What template was used for this submission?")

    class Meta:
        ordering = ('-completed_at', 'status', 'slug',)

    def __str__(self):
        return f"""{ self.submission_id } / { self.template } / { self.slug } / { self.status } / {self.completed_at }"""
    
    def _auto_name(self, name):
        """ automatically update the associated submitter's name if it looks like an email address. """
        submitters = [dss.submitter for dss in DocusealSubmitterSubmission.objects.filter(submission=self)]
        for submitter in submitters:
            person = PersonDocuseal.objects.get(submitter=submitter).person
            if "@" in person.name and "." in person.name:
                if "@" not in name and "." not in name:
                    # print(f"Updating: {person.name}==>{name}")
                    Log.new(logging_level=logging.INFO, description="Auto-name by Docuseal", json={'old': person.name, 'new': name})
                    person.name = name
                    person.save()

    def create_or_update(submission_id):
        """ update a record if it exists, else create one """
        json = {'submission_id': submission_id}

        submission_api = docuseal.get_submission(submission_id)
        submission_qs = DocusealSubmission.objects.filter(submission_id=submission_id)
        submitters_api = [{'submitter_id': s['id'], 'email': s['email'], 'slug': s['slug'], 'status': s['status'], 'role': s['role']} for s in submission_api['submitters']]
        # print(f"submitters_api: {submitters_api}")
        if submission_qs.exists():
            submission = submission_qs.first()
            # assuming slug can't change
            submission.status = submission_api['status']
            submission.created_at = submission_api['created_at']
            submission.completed_at = submission_api['completed_at']
            if submission_api['archived_at']:
                submission.archived_at = submission_api['archived_at']
            submission.save()
            submitters_db = DocusealSubmitterSubmission.objects.filter(submission=submission).values_list('id')
            # print(f"submitters_db: {submitters_db}")
            submitters_new = [s for s in submitters_api if s['submitter_id'] not in submitters_db]
            # print(f"submitters_new: {submitters_new}")
            if submitters_new:
                for s in submitters_new:
                    DocusealSubmitter.create_if_needed_by_id(s['submitter_id'])
                    submitter = DocusealSubmitter.objects.get(submitter_id=s['submitter_id'])
                    DocusealSubmitterSubmission.objects.create(submission=submission, submitter=submitter)
            Log.new(logging_level=logging.DEBUG, description="Update DocusealSubmission", json={'submission_id': submission_id})
        else:
            DocusealSubmission.new(submission_id, submission_api['slug'], submission_api['status'], submission_api['created_at'], submission_api['completed_at'], submission_api['archived_at'], submission_api['template']['id'], submitters_api)
            Log.new(logging_level=logging.DEBUG, description="Create DocusealSubmission", json=json)

    def new(submission_id, slug, status, created_at, completed_at, archived_at, template_id, submitters=None):
        """ Create a new instance """
        template = DocusealTemplate.objects.get(template_id=template_id)
        doc_sub = DocusealSubmission.objects.create(submission_id=submission_id, slug=slug, status=status, created_at=created_at, completed_at=completed_at, archived_at=archived_at, template=template)
        Log.new(logging_level=logging.DEBUG, description="Create DocusealSubmission", json={'submission_id': submission_id})
        for s in submitters:
            DocusealSubmitter.create_if_needed_by_id(submitter_id=s['submitter_id'])
            submitter = DocusealSubmitter.objects.get(submitter_id=s['submitter_id'])
            DocusealSubmitterSubmission.objects.create(submission=doc_sub, submitter=submitter)

    def refresh(new_only=True):
        """ clear out existing records and repopulate them from the API """
        if new_only:
            Log.new(logging_level=logging.INFO, description="Fetch New DocusealSubmission")
            # capture changes to submission status/dates
            for submission in DocusealSubmission.objects.filter(completed_at__isnull=True).order_by('-created_at')[:20]:
                DocusealSubmission.create_or_update(submission.submission_id)
            last_submission_id = DocusealSubmission.objects.all().order_by('-submission_id').first().submission_id
        else:
            Log.new(logging_level=logging.INFO, description="Refresh DocusealSubmission")
            DocusealSubmission.objects.all().delete()
            last_submission_id = None

        pagination_next = True
        while pagination_next:
            api_dict = {'limit': 100}
            if last_submission_id:
                if new_only:
                    sort_word = 'before'
                else:
                    sort_word = 'after'
                api_dict[sort_word] = last_submission_id
            
            submissions = docuseal.list_submissions(api_dict)
            
            last_submission_id = submissions['pagination']['next']
            if not last_submission_id:
                pagination_next = False

            for submission in submissions['data']:
                if submission['status'] == 'completed':
                    submitters = [{'submitter_id': s['id'], 'status': s['status'], 'role': s['role']} for s in submission['submitters']]
                    if DocusealTemplate.objects.filter(template_id=submission['template']['id']).exists():
                        DocusealSubmission.new(submission['id'], submission['slug'], submission['status'], submission['created_at'], submission['completed_at'], submission['archived_at'], submission['template']['id'], submitters)

    def get_url(self):
        """ URL for a hyperlink """
        return f"{ DOCUSEAL_WWW_ENDPOINT }/submissions/{ self.submission_id }"


class DocusealSubmitter(models.Model):
    """ A Docuseal submitter - often per documents """
    submitter_id = models.PositiveIntegerField(help_text="What is the Docuseal ID of this submitter?")
    email = models.EmailField(help_text="What is the email address of this submitter?")
    slug = models.CharField(max_length=32, help_text="What is the URL slug for this submitter?")

    class Meta:
        ordering = ('email', 'slug',)

    def __str__(self):
        return f"""{ self.submitter_id } / { self.email } / { self.slug }"""
    
    def _auto_associate(self):
        """ automatically associate this submitter with the first person 
        it finds that shares this email address. if none is found create a Person for it. """
        if not PersonDocuseal.objects.filter(submitter__id=self.submitter_id):
            # print("new person-docuseal")
            person = None
            email = PersonEmail.objects.filter(email=self.email).first()
            if email:
                # print(f"found email: {email}")
                person = email.person
            if person:
                # print(f"found person: {person}")
                # print("creating docuseal-person")
                PersonDocuseal.objects.create(person=person, submitter=self)
            else:
                # print(f"could not find person with email: {email}")
                # print("creating person")
                person = Person.objects.create(name=self.email)
                # print("linking email")
                email = PersonEmail.objects.create(person=person, email=self.email)
                person.preferred_email = email
                person.save()
                # print("creating docuseal-person")
                PersonDocuseal.objects.create(person=person, submitter=self)

    def create_if_needed_by_id(submitter_id):
        """ Create a new DocusealSubmitter if one with this email doesn't exist already """
        if not DocusealSubmitter.objects.filter(submitter_id=submitter_id).exists():
            submitter = docuseal.get_submitter(submitter_id)
            if submitter:
                DocusealSubmitter.new(submitter['id'], submitter['email'], submitter['slug'])

    def create_if_needed(email):
        """ Create a new DocusealSubmitter if one with this email doesn't exist already """
        if not DocusealSubmitter.objects.filter(email=email).exists():
            for submitter in docuseal.list_submitters({'q': email})['data']:
                DocusealSubmitter.new(submitter['id'], submitter['email'], submitter['slug'])

    def new(submitter_id, email, slug):
        """ Create a new instance and auto_associate """
        doc_sub = DocusealSubmitter.objects.create(submitter_id=submitter_id, email=email, slug=slug)
        Log.new(logging_level=logging.DEBUG, description="Create DocusealSubmitter", json={'submitter_id': submitter_id})
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

    def refresh(new_only=False):
        """ clear out existing records and repopulate them from the API """
        if new_only:
            Log.new(logging_level=logging.INFO, description="Fetch New DocusealSubmitter")
            last_submitter_id = DocusealSubmitter.objects.all().order_by('-submitter_id').first().submitter_id
        else:
            Log.new(logging_level=logging.INFO, description="Refresh DocusealSubmitter")
            DocusealSubmitter.objects.all().delete()
            last_submitter_id = None

        pagination_next = True
        while pagination_next:
            api_dict = {'limit': 100}
            if last_submitter_id:
                if new_only:
                    sort_word = 'before'
                else:
                    sort_word = 'after'
                api_dict[sort_word] = last_submitter_id
            
            submitters = docuseal.list_submitters(api_dict)
            
            last_submitter_id = submitters['pagination']['next']
            if not last_submitter_id:
                pagination_next = False

            for submitter in submitters['data']:
                DocusealSubmitter.new(submitter['id'], submitter['email'], submitter['slug'])


class DocusealSubmitterSubmission(models.Model):
    """ A map between Docuseal submitter and  submission """
    submitter = models.ForeignKey("subwaive.DocusealSubmitter", blank=True, null=True, on_delete=models.CASCADE, help_text="Who is the submitter for this submission?")
    submission = models.ForeignKey("subwaive.DocusealSubmission", blank=True, null=True, on_delete=models.CASCADE, help_text="What submission did this submitter submit?")

    class Meta:
        ordering = ('submitter', 'submission',)

    def __str__(self):
        return f"""{ self.submitter } / { self.submission }"""
    

class DocusealTemplate(models.Model):
    """ A Docuseal template """
    template_id = models.PositiveIntegerField(help_text="What is the Docuseal ID of this template?")
    folder_name = models.CharField(max_length=128, help_text="What folder id this template under in Docuseal?")
    name = models.CharField(max_length=128, help_text="What is the name of this template?")
    slug = models.CharField(max_length=32, help_text="What is the URL slug for this template?")

    class Meta:
        ordering = ('folder_name', 'name', 'slug',)

    def __str__(self):
        return f"""{ self.template_id } / { self.folder_name } / { self.name } / { self.slug }"""

    def create_or_update_by_id(template_id):
        """ Create a template by Id instead of API row """
        DocusealTemplate.create_or_update(template_api=docuseal.get_template(template_id))

    def create_or_update(template_api):
        """ Update a template by API row if it exists, otherwise create it """
        template_id = template_api['id']
        template_qs = DocusealTemplate.objects.filter(template_id=template_id)
        if template_qs.exists():
            template = template_qs.first()
            template.name = template_api['name']
            template.folder_name = template_api['folder_name']
            template.save()
            Log.new(logging_level=logging.DEBUG, description="Update DocusealTemplate", json={'template_id': template_id})
        else:
            DocusealTemplate.new(template_api['id'], template_api['folder_name'], template_api['name'], template_api['slug'])

    def new(template_id, folder_name, name, slug):
        """ Create a new instance and auto_associate """
        DocusealTemplate.objects.create(template_id=template_id, folder_name=folder_name, name=name, slug=slug)
        Log.new(logging_level=logging.DEBUG, description="Create DocusealTemplate", json={'template_id': template_id})

    def refresh(new_only=False):
        """ clear out existing records and repopulate them from the API """
        if new_only:
            Log.new(logging_level=logging.INFO, description="Fetch New DocusealTemplate")
            last_template_id = DocusealTemplate.objects.all().order_by('-template_id').first().template_id
        else:
            Log.new(logging_level=logging.INFO, description="Refresh DocusealTemplate")
            last_template_id = None
            DocusealTemplate.objects.all().delete()

        pagination_next = True
        while pagination_next:
            api_dict = {'limit': 100}
            if last_template_id:
                if new_only:
                    sort_word = 'before'
                else:
                    sort_word = 'after'
                api_dict[sort_word] = last_template_id
            
            templates = docuseal.list_templates(api_dict)
            
            last_template_id = templates['pagination']['next']
            if not last_template_id:
                pagination_next = False

            for template in templates['data']:
                DocusealTemplate.create_or_update(template)

    def get_url(self):
        """ URL for a hyperlink """
        return f"{ DOCUSEAL_WWW_ENDPOINT }/d/{ self.slug }"
    

class CalendarEvent(models.Model):
    """ An event from an ical file """
    UID = models.UUIDField(help_text="What is the ical UID of this calendar event?")
    """ Part of a composite key with recurrence_order.\n
    UIDs are shared by recurrences, which means they are not useful 
    individually as a key. Since RECURRENCE_ID can change when the SEQUENCE changes, we instead 
    assume that the order of recurrences is stable for past events. """
    recurrence_order = models.IntegerField(default=1, help_text="What is the ical recurrence_order of this calendar event?")
    """ Part of a composite key with UID.\n 
    An ordinal sequence number. Assumed to be stable for past events, 
    provided old events are not added to an existing series. """
    summary = models.CharField(max_length=512, help_text='What is the calendar event summary?')
    description = models.TextField(max_length=2048, help_text='What is the calendar event description?')
    start = models.DateTimeField(help_text='When does the calendar event begin?')
    end = models.DateTimeField(help_text='When does the calendar event finish?')

    class Meta:
        ordering = ('-start', 'summary',)

    def __str__(self):
        return f"""{ self.summary[:50] } / { self.start } / { self.end }"""
    
    def _auto_associate(self, lbound=None):
        """ automatically create an event for this calendar event if it is in the future and an event does not exist. """
        if not lbound:
            lbound = datetime.datetime.now().astimezone(pytz.timezone(TIME_ZONE))
        if self.start >= lbound:
            # print("is after lbound")
            event_qs = Event.objects.filter(summary=self.summary, start=self.start, end=self.end)
            if not event_qs.exists():
                Event.objects.create(summary=self.summary, description=self.description, start=self.start, end=self.end, calendar_event=self)
        # else:
        #     print("out-of-update-date-range event")
    
    def create(event_values, lbound=None):
        """ create a new event from a dict """
        # print("creating cal event")
        event = CalendarEvent.objects.create(
            UID=event_values['uid'], recurrence_order=event_values['recurrence_order'], 
            summary=event_values['summary'], 
            description=event_values['description'], 
            start=event_values['start'], end=event_values['end'])
        event._auto_associate(lbound)
        Log.new(logging_level=logging.DEBUG, description="Create CalendarEvent", json={'uid': event.UID})

    def get_event_list_from_calendar_url(url, lbound=None, ubound=None):
        """ return a sorted list of events from a calendar URL """
        if not lbound:
            lbound = datetime.date.today()+datetime.timedelta(days=-30)
        if not ubound:
            ubound = datetime.date.today()+datetime.timedelta(days=60)
        with caldav.DAVClient(url=CALENDAR_URL) as client:
            principal = client.principal()

            calendars = principal.calendars()
            if calendars:
                events_prelim = calendars[0].search(
                    start=lbound,
                    end=ubound,
                    event=True,
                    expand=True)
                
                events = [e.icalendar_instance.events[0] for e in events_prelim]
                events = sorted(events, key=lambda x: x.start)

                return events

    def refresh(request):
        """ Refresh events from ical URL """
        lbound = None
        ubound = None
        json = {'type': 'full'}
        if request.POST:
            lbound = request.POST.get("lbound")
            lbound = datetime.datetime.strptime(lbound, "%Y-%m-%d").astimezone(pytz.timezone(TIME_ZONE))
            ubound = request.POST.get("ubound")
            ubound = datetime.datetime.strptime(ubound, "%Y-%m-%d").astimezone(pytz.timezone(TIME_ZONE))
            json = {'type': 'time-bounded', 'lbound': lbound.isoformat(), 'ubound': ubound.isoformat()}

        events = CalendarEvent.get_event_list_from_calendar_url(CALENDAR_URL, lbound, ubound)
        CalendarEvent.objects.all().delete()
        Event.clear_future_unused()
        
        uid_count = {}
        for e in events:
            uid = e.get("UID")

            if uid in uid_count.keys():
                uid_count[uid] += 1
            else:
                uid_count[uid] = 1

            is_process = True
            if lbound and ubound:
                is_process = False
                if e.start.astimezone(pytz.timezone(TIME_ZONE)) >= lbound \
                    and e.start.astimezone(pytz.timezone(TIME_ZONE)) <= ubound:
                    is_process = True
            if is_process:
                recurrence_order = uid_count[uid]
                event_values = {
                    'uid': uid,
                    'summary': e.get("SUMMARY").__str__().strip(),
                    'description': e.get("DESCRIPTION").__str__().strip()[:2048],
                    'start': e.start.astimezone(pytz.timezone(TIME_ZONE)),
                    'end': e.end.astimezone(pytz.timezone(TIME_ZONE)),
                    'recurrence_order': recurrence_order,
                }

                event_qs = CalendarEvent.objects.filter(UID=uid, recurrence_order=recurrence_order)
                
                if event_qs.exists():
                    # print("update")
                    CalendarEvent.update_event(event_qs.first(), event_values)

                else:
                    # print("create")
                    CalendarEvent.create(event_values, lbound)

        if uid_count:
            Log.new(logging_level=logging.INFO, description="Refresh Event", json=json)

    def refresh_event(self):
        """ Refresh a single event """
        events = CalendarEvent.get_event_list_from_calendar_url(CALENDAR_URL)
        recurrence_order = 0
        for e in events:
            uid = e.get("UID")
            if uid==str(self.UID):
                recurrence_order += 1
                if recurrence_order == self.recurrence_order:
                    event_values = {
                        'uid': uid,
                        'summary': e.get("SUMMARY").__str__().strip(),
                        'description': e.get("DESCRIPTION").__str__().strip()[:2048],
                        'start': e.start.astimezone(pytz.timezone(TIME_ZONE)),
                        'end': e.end.astimezone(pytz.timezone(TIME_ZONE)),
                        'recurrence_order': recurrence_order,
                    }
                    CalendarEvent.update_event(self, event_values)
                    break

    def update_event(event, event_values):
        """ Update an event record """
        is_updated = False
        json = {'uid': event_values['uid'], 'recurrence_order': event_values['recurrence_order']}

        if event.summary != event_values['summary']:
            is_updated = True
            json['summary_updated'] = True
            event.summary = event_values['summary']

        if event.description != event_values['description']:
            is_updated = True
            json['description_updated'] = True
            event.description = event_values['description']

        if event.start != event_values['start']:
            is_updated = True
            json['start_old'] = event.start.isoformat()
            event.start = event_values['start']

        if event.end != event_values['end']:
            is_updated = True
            json['end_old'] = event.end.isoformat()
            event.end = event_values['end']

        if is_updated:
            event.save()
            Log.new(logging_level=logging.DEBUG, description="Update Event", json=json)


class Event(models.Model):
    """ An event for storing attendance.
    iCal files are not stable enough to use as a database. Changed to dates or times can make difficult to track changes
    that make database entries related to them point to incorrect events.

    To avoid this messiness, we dump and rebuild calendar events when we refresh, and events that are in the future and have
    no person event records. Calendar event instances that are in the future automatically create event instances to 
    match. Calendar events can be selected as the source for an event from the admin console if needed (such as using a future event 
    to backfill a missing historical event you might want to populate).

    Three consequences to understand:
    1. To prevent a future event from being over-written, add a check-in
    2. To rebuild a past event, use the admin console to change the calendar event it points to
    3. When rebuilding a past event like this, rerun the event refresh to rebuild the canabalized future event
    """
    summary = models.CharField(max_length=512, help_text='What is the event summary?')
    description = models.TextField(max_length=2048, help_text='What is the event description?')
    start = models.DateTimeField(help_text='When does the event begin?')
    end = models.DateTimeField(help_text='When does the event finish?')
    calendar_event = models.ForeignKey("subwaive.CalendarEvent", blank=True, null=True, on_delete=models.SET_NULL, help_text="Which calendar event is this based on?")

    class Meta:
        ordering = ('-start', 'summary',)

    def __str__(self):
        return f"""{ self.id } / { self.summary[:50] } / { self.start } / { self.end }\n"""
    
    def clear_future_unused():
        """ delete instances that are both in the future and have no associated check-ins """
        events = Event.objects.exclude(attendee__isnull=False).filter(start__gt=datetime.datetime.now().astimezone(pytz.timezone(TIME_ZONE)))
        # print(events)
        events.delete()
        Log.new(logging_level=logging.DEBUG, description="Clear unused, future Event instances")

    def get_current_event():
        """ return any Event objects for events that are currently happening """
        return Event.objects.filter(start__lte=datetime.datetime.now().astimezone(pytz.timezone(TIME_ZONE)), end__gte=datetime.datetime.now().astimezone(pytz.timezone(TIME_ZONE)))

    def refresh_local_data(self):
        """ refresh details for self.calendar_event """
        self.summary = self.calendar_event.summary
        self.start = self.calendar_event.start
        self.end = self.calendar_event.end
        self.save()

    # def save(self):
    # override save to look for cal event changes and to update the local data accordingly unless the local data was changed


class Log(models.Model):
    """ Log activities """
    timestamp = models.DateTimeField(auto_now_add=True, help_text='When was the event logged?')
    description = models.CharField(max_length=512, help_text='What happened?')
    other_info = models.TextField(max_length=4096, blank=True, null=True, help_text='What additional detail helps describe the event?')
    json = models.JSONField(blank=True, null=True, help_text="What JSON describes the event?")
    logging_level = models.IntegerField(default=0, help_text='What is the Python logging level of the event?')

    class Meta:
        ordering = ('-timestamp',)

    def __str__(self):
        return f"""{ self.timestamp } / { self.logging_level } / { self.description[:32] }"""
    
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

    def new(logging_level, description, json=None, other_info=None):
        if logging_level >= LOGGING_LEVEL:
            Log.objects.create(description=description, json=json, other_info=other_info, logging_level=logging_level)


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
    name = models.CharField(max_length=128, help_text="What is the preferred name for ths person?")
    preferred_email = models.ForeignKey("subwaive.PersonEmail", related_name="+", blank=True, null=True, on_delete=models.CASCADE, help_text="What is this person's preferred email address?")
    is_nfc_admin = models.BooleanField(default=False, help_text="Is this person allowed to see NFC terminal config debrief?")
    #!!! extract nfc_admin to group?
     
    class Meta:
        ordering = ('name', 'preferred_email__email',)

    def __str__(self):
        return f"""{ self.name } / { self.preferred_email }"""
    
    def check_in(self, event_id=None):
        """ check the person into an event """
        print("checking in...")
        if event_id:
            event = Event.objects.get(id=event_id)
        else:
            event = None
        return PersonEvent.objects.create(person=self, event=event)
    
    def check_membership_status_by_person_id(person_id):
        return Person.objects.get(id=person_id).check_membership_status()
    
    def check_membership_status(self):
        """ return true if they have a current membership """
        status = None
        memberships = self.get_memberships()
        if memberships:
            status = 'active'
            for m in memberships:
                if m['status']!='active':
                    status = m['status']

        return status 
    
    def check_waiver_status_by_person_id(person_id):
        return Person.objects.get(id=person_id).check_waiver_status()
    
    def check_waiver_status(self):
        """ determine if a given person has a signed waiver """
        submitters = PersonDocuseal.objects.filter(person=self).values_list('submitter')
        waivers = DocusealSubmitterSubmission.objects.filter(
            submitter__in=submitters,
            submission__template__folder_name='Waivers',
            submission__status='completed'
            )
        return waivers.exists()

    def get_last_check_in(self):
        """ return the last check-in for a person """
        return PersonEvent.objects.filter(person=self).order_by('-check_in_time').first()

    def get_submissions(self, lifecycle_state):
        """ fetch links to each document the person has signed """
        submitters = PersonDocuseal.objects.filter(person=self).values_list('submitter')
        dss = DocusealSubmitterSubmission.objects.filter(submitter__in=submitters).values_list('submission__id')
        submissions = DocusealSubmission.objects.filter(id__in=dss)
        if lifecycle_state == "archived":
            submissions = submissions.filter(archived_at__isnull=False)
        elif lifecycle_state == "pending":
            submissions = submissions.filter(completed_at__isnull=True)
        else:        
            submissions = submissions.filter(archived_at__isnull=True)

        return submissions.order_by('template__folder_name')
        
    def get_documents(self, lifecycle_state):
        """ fetch links to each document the person has signed """
        submissions = self.get_submissions(lifecycle_state)
        
        documents = [
            {
                'folder_name': doc.template.folder_name,
                'template_name': doc.template.name,
                'status': doc.status,
                'archived_at': doc.archived_at,
                'created_at': doc.created_at,
                'completed_at': doc.completed_at,
                'url': doc.get_url(),
                'important_fields': [{'field': f.field, 'value': f.value} for f in DocusealFieldStore.objects.filter(submission=doc)]
            }
            for doc in submissions
        ]

        return documents

    def get_events(self, is_today=False):
        """ fetch a list of events purchased """
        return self.get_onetime_payments(payment_type="event", is_today=is_today)

    def get_day_passes(self, is_today=False):
        """ fetch a list of day-passes purchased """
        return self.get_onetime_payments(product_name="day pass", is_today=is_today)

    def get_donor_status(self):
        """ give a categorical description of how much they've donated """
        otp = self.get_onetime_payments(payment_type="donation")
        
        donor_status = [False, 0]
        if self.get_subscriptions("donation"):
            donor_status[0] = True
        if otp:
            donor_status[1] = len(otp)

        return donor_status

    def get_email_list(self):
        """ return a list of emails associated with this person """
        return PersonEmail.objects.filter(person=self)

    def get_memberships(self):
        """ fetch a list of memberships """
        return self.get_subscriptions("membership")

    def get_onetime_payments(self, product_name=None, payment_type=None, is_today=False):
        """ fetch data on each one-time purchase the person has made """
        # Get a list of OTP for this person
        # print(f"payment_type: {payment_type}")
        # print(f"product_name: {product_name}")
        stripe_customers = [ps.customer for ps in PersonStripe.objects.filter(person=self)]
        # print(f"stripe_customers: {stripe_customers}")
        payments = StripeOneTimePayment.objects.filter(customer__in=stripe_customers)
        if is_today:
            payments = payments.filter(date=datetime.date.today())
        # print(f"payments: {payments}")

        # Find associated PL.Prc.Prdt.Names
        otp = []
        for p in payments:
            prices = StripePaymentLinkPrice.objects.filter(payment_link=p.payment_link)
            if payment_type == "donation":
                prices = prices.filter(price__product__name__icontains="donation")
            elif payment_type == "event":
                prices = prices.filter(payment_link__date__isnull=False)
            else:
                prices = prices.filter(payment_link__date__isnull=True).exclude(price__product__name__icontains="donation")

            # print(f"prices: {prices}")
            for plp in prices:
                if payment_type == "event":
                    otp_date = p.payment_link.date
                else:
                    otp_date = p.date
                otp.append(
                    {
                        'description': plp.price.product.name, 
                        'date': otp_date,
                    }
                )

        # print(f"otp: {otp}")

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

        Log.new(logging_level=logging.INFO, description="Merge Person", json={'person_id': self.id, 'merge_child_id': merge_child_id})
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

        pes = PersonEvent.objects.filter(person=merge_child)
        for pe in pes:
            pe.person = self
            pe.save()

        merge_child.delete()

    def search(search_term):
        """ search for a Person """
        emails = PersonEmail.objects.filter(Q(person__name__icontains=search_term)|Q(email__icontains=search_term))

        field_submissions = DocusealFieldStore.objects.filter(value__icontains=search_term).values_list('submission')
        submitters = DocusealSubmitterSubmission.objects.filter(submission__in=field_submissions).values_list('submitter')
        persons = PersonDocuseal.objects.filter(submitter__in=submitters)
        
        person_id_list = set(
            [pe.person.id for pe in emails]
            + [s.person.id for s in persons]
            )

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
    person = models.ForeignKey("subwaive.Person", on_delete=models.CASCADE, help_text="Who is the person associated with this email address?")
    email = models.EmailField(help_text="What is this person's email address?")

    class Meta:
        ordering = ('person', 'email',)

    def __str__(self):
        return f"""{ self.person.name } / { self.email }"""

    def unmerge(self):
        """ Break linkages between self and an email address (including Stripe and Docuseal accounts)"""
        # print('unmerge')
        email = self.email
        # print("pre-delete",email)
        person_id = self.person.id
        # print(person_id)

        Log.new(logging_level=logging.INFO, description="Unmerge Person", json={'person_id': person_id, 'email': email})

        PersonStripe.objects.filter(person__id=person_id).delete()
        PersonDocuseal.objects.filter(person__id=person_id).delete()
        self.delete()
        # print("post-delete",email)

        for ds in DocusealSubmitter.objects.filter(email=email):
            # print(ds)
            ds._auto_associate()

        for sc in StripeCustomer.objects.filter(email=email):
            # print(sc)
            sc._auto_associate()


class PersonEvent(models.Model):
    """ A map between Person and Event """
    person = models.ForeignKey("subwaive.Person", on_delete=models.CASCADE, help_text="Who is the person checked-in to this event?")
    event = models.ForeignKey("subwaive.Event", on_delete=models.CASCADE, blank=True, null=True, related_name="attendee", help_text="What event is associated with this check-in?")
    check_in_time = models.DateTimeField(auto_now_add=True, help_text="When was the check-in logged?")

    class Meta:
        ordering = ('-check_in_time', 'person', 'event',)

    def __str__(self):
        return f"""{ self.check_in_time } / { self.person } / { self.event }"""

    def check_prior_check_in(person_id, event_id):
        """ check if a person has already been checked in to an event """
        last_check_in = PersonEvent.objects.filter(person__id=person_id, event__id=event_id)
        is_checked_in = False
        if last_check_in.exists():
                is_checked_in = True
        return is_checked_in
    

class PersonStripe(models.Model):
    """ A map between Person and StripeCustomer """
    person = models.ForeignKey("subwaive.Person", on_delete=models.CASCADE, help_text="Who is the person associated with this Stipe customer?")
    customer = models.ForeignKey("subwaive.StripeCustomer", on_delete=models.CASCADE, help_text="What is the Stripe customer id associated with this person?")

    class Meta:
        ordering = ('person', 'customer',)

    def __str__(self):
        return f"""{ self.person } / { self.customer.stripe_id }"""
    

class Phone(models.Model):
    """ A phone number for a person """
    phone_number = models.CharField(max_length=10, help_text="What is your phone number?")
    person = models.ForeignKey("subwaive.Person", on_delete=models.CASCADE, blank=True, null=True, help_text="Who is the person associated with this phone number?")
    phone_id = models.CharField(max_length=32, help_text="What is the URL secret for registering this phone number?")
    activation_id = models.CharField(max_length=32, help_text="What is the URL secret used to activate this phone number?")
    is_active = models.BooleanField(default=False, help_text="Has this phone number been activated?")


class NFC(models.Model):
    """ An NFC token for a person """
    uid = models.CharField(max_length=32, help_text="UID identifying this NFC")
    person = models.ForeignKey("subwaive.Person", on_delete=models.CASCADE, blank=True, null=True, help_text="Person associated with this NFC token?")
    nfc_id = models.CharField(max_length=32, help_text="What is the URL secret used to register this NFC token?")
    activation_id = models.CharField(max_length=32, help_text="What is the URL secret used to activate this NFC token?")
    is_active = models.BooleanField(default=False, help_text="Has this NFC token been activated?")


class QRCategory(models.Model):
    """ Categories for organizing QR codes """
    name = models.CharField(max_length=64, help_text="What is the name of the QR code category?")
    is_sensitive = models.BooleanField(default=False, help_text="Should this link be hidden from unauthenticated viewers?")

    class Meta:
        ordering = ('is_sensitive', 'name',)

    def __str__(self):
        sensitivity_label = "PUBLIC"
        if self.is_sensitive:
            sensitivity_label = "SENSITIVE"
        return f"""{ sensitivity_label } / { self.name }"""


class QRCustom(models.Model):
    """ User-defined QR codes """
    name = models.CharField(max_length=64, help_text="What is the name of the QR code?")
    category = models.ForeignKey("subwaive.QRCategory", on_delete=models.CASCADE, help_text="What category does this QR code belong to?")
    content = models.CharField(max_length=4096, help_text="What is the QR code's payload?")

    class Meta:
        ordering = ('category__name', 'name',)

    def __str__(self):
        return f"""{ self.category.name } / { self.name }"""


class StripeCustomer(models.Model):
    """ A Stripe Customer """
    stripe_id = models.CharField(max_length=64, blank=True, null=True, help_text="What is the Stripe ID of this customer?")
    name = models.CharField(max_length=128, help_text="What is the name of this customer?")
    email = models.EmailField(help_text="What is the email address of this customer?")

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
                if "@" in person.name and "." in person.name:
                    if "@" not in self.name and "." not in self.name:
                        Log.new(logging_level=logging.INFO, description="Auto-name by Stripe", json={'old': person.name, 'new': self.name})
                        person.name=self.name
                        person.save()
            else:
                person = Person.objects.create(name=self.name)
                email = PersonEmail.objects.create(person=person, email=self.email)
                person.preferred_email = email
                person.save()

    def create_and_or_return(stripe_id=None,email=None): #!!! prefer stripe_id, fallback email, if email then no stripe_id
        """ return a record if it exists, else create and return it """
        if stripe_id:
            json = {'stripe_id': stripe_id}

            customer_qs = StripeCustomer.objects.filter(stripe_id=stripe_id)
            if customer_qs.exists():
                customer = customer_qs.first()
            else:
                api_record = stripe.Customer.retrieve(stripe_id)
                customer = StripeCustomer.objects.create(stripe_id=stripe_id, name=api_record.name, email=api_record.email)
                Log.new(logging_level=logging.DEBUG, description="Create StripeCustomer", json=json)
        elif email:
            json = {'stripe_id': email}

            customer_qs = StripeCustomer.objects.filter(email=email)
            if customer_qs.exists():
                customer = customer_qs.first()
            else:
                api_record = stripe.Customer.retrieve(stripe_id) #!!! stripe_id is null here
                customer = StripeCustomer.objects.create(stripe_id=None, name=api_record.name, email=api_record.email)
                Log.new(logging_level=logging.DEBUG, description="Create StripeCustomer", json=json)


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
            Log.new(logging_level=logging.DEBUG, description="Update StripeCustomer", json=json)
        else:
            StripeCustomer.objects.create(stripe_id=stripe_id, name=api_record.name, email=api_record.email)
            Log.new(logging_level=logging.DEBUG, description="Create StripeCustomer", json=json)


    def get_url(self):
        """ URL for a hyperlink """
        return f"{ STRIPE_WWW_ENDPOINT }/customers/{ self.stripe_id }"

    def new(stripe_id, name, email):
        sc = StripeCustomer.objects.create(stripe_id=stripe_id, name=name, email=email)
        Log.new(logging_level=logging.DEBUG, description="Create StripeCustomer", json={'stripe_id': stripe_id})
        sc._auto_associate()

    def search(name, email):
        """ search for a Stripe customer from the API """
        pass

    def refresh(new_only=False):
        """ clear out existing records and repopulate them from the API """
        Log.new(logging_level=logging.INFO, description="Refresh StripeCustomer")
        StripeCustomer.objects.all().delete()
        for customer in stripe.Customer.list().auto_paging_iter():
            stripe_id = customer['id']
            name = customer['name'][:128]
            email = customer['email'][:128]
            StripeCustomer.new(stripe_id=stripe_id, name=name, email=email)


class StripeOneTimePayment(models.Model):
    """ A Stripe one-time payment """
    stripe_id = models.CharField(max_length=128, help_text="What is the Stripe ID of this checkout session?")
    customer = models.ForeignKey("subwaive.StripeCustomer", on_delete=models.CASCADE, help_text="What Stripe Customer is associated with this checkout session?")
    date = models.DateField(null=True, blank=True, help_text="What is date is associated with the payment link or what was the date the checkout session occurred?") #!!! if we store paymentlink, why muddle this field's contents?
    status = models.CharField(max_length=64, help_text="What is the status of tis checkout session?")
    payment_link = models.ForeignKey("subwaive.StripePaymentLink", on_delete=models.CASCADE, help_text="What payment link was used to initiate this checkout session?")

    class Meta:
        ordering = ('stripe_id',)

    def __str__(self):
        return f"""{ self.stripe_id } / { self.payment_link } / { self.date }"""

    def create_if_needed(checkout_session):
        """ creates a new record """
        json = {'stripe_id': checkout_session.stripe_id}
        
        if checkout_session.status == 'complete':
            payment_qs = StripeOneTimePayment.objects.filter(stripe_id=checkout_session.id)
            if not payment_qs.exists():
                customer = None
                email = checkout_session.customer_details['email']
                name = checkout_session.customer_details['name']
                if not name:
                    name = email
                customer_qs = StripeCustomer.objects.filter(email=email)
                # print('checking for customer', email)
                if customer_qs.exists():
                    # print('using existing customer')
                    customer = customer_qs.first()
                else:
                    # print('creating new customer')
                    StripeCustomer.new(stripe_id=None, name=name, email=email)
                    customer = StripeCustomer.objects.get(email=email)
                    # print(customer)

                payment_link_qs = StripePaymentLink.objects.filter(stripe_id=checkout_session.payment_link)
                if payment_link_qs.exists():
                    payment_link = payment_link_qs.first()
                else:
                    payment_link = StripePaymentLink.create_or_update(checkout_session.payment_link)
                
                if payment_link.date:
                    otp_date = payment_link.date
                else:
                    otp_date = fromtimestamp(checkout_session.created).date()

                StripeOneTimePayment.objects.create(stripe_id=checkout_session.id, customer=customer, date=otp_date, status=checkout_session.status, payment_link=payment_link)
                Log.new(logging_level=logging.DEBUG, description="Create StripeOneTimePayment", json=json)

    def get_session(stripe_id):
        """ return a session from the API for a given ID"""
        return stripe.checkout.Session.retrieve(stripe_id)

    def get_url(self):
        """ URL for a hyperlink """
        return f"{ STRIPE_WWW_ENDPOINT }/payments/{ self.stripe_id }"

    def refresh(new_only=False):
        """ clear out existing records and repopulate them from the API """
        Log.new(logging_level=logging.INFO, description="Refresh StripeOneTimePayment")
        StripeOneTimePayment.objects.all().delete()
        for plp in StripePaymentLinkPrice.objects.filter(payment_link__is_recurring=False):
            for cs in stripe.checkout.Session.list(payment_link=plp.payment_link.stripe_id):
                StripeOneTimePayment.create_if_needed(cs)


class StripePaymentLink(models.Model):
    """ A Stripe PaymentLink """
    stripe_id = models.CharField(max_length=64, help_text="What is the Stripe ID of this payment link?")
    url = models.URLField(help_text="What is the URL of this payment link?")
    is_recurring = models.BooleanField(default=False, help_text="Is this payment link for a recurring charge?")
    date = models.DateField(blank=True, null=True, help_text="What event_date was provided in the payment link metadata?")
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
            Log.new(logging_level=logging.DEBUG, description="Create StripePaymentLink", json=json)
            plink.create_or_update_children()

    def create_or_update_children(self):
        """ updates existing child records, otherwise creates them """
        for line_item in stripe.PaymentLink.list_line_items(self.stripe_id).auto_paging_iter():
            price = StripePrice.create_or_update(line_item.price.id)
            StripePaymentLinkPrice.create_if_needed(payment_link=self, price=price)

    def get_url(self):
        """ URL for a hyperlink """
        return f"{ STRIPE_WWW_ENDPOINT }/payment-links/{ self.stripe_id }"

    def refresh(new_only=False):
        """ clear out existing records and repopulate them from the API """
        Log.new(logging_level=logging.INFO, description="Refresh StripePaymentLink")
        StripePaymentLink.objects.all().delete()
        for payment_link in stripe.PaymentLink.list().auto_paging_iter():
            if payment_link.subscription_data:
                is_recurring = True
            else:
                is_recurring = False
            if "event_date" in payment_link.metadata.keys():
                event_date = datetime.datetime.strptime(payment_link.metadata.get("event_date"), "%Y-%m-%d")
            else:
                event_date = None
            StripePaymentLink.objects.create(stripe_id=payment_link.id, url=payment_link.url, is_recurring=is_recurring, date=event_date)
            Log.new(logging_level=logging.DEBUG, description="Create StripePaymentLink", json={'stripe_id': payment_link.id})



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
            Log.new(logging_level=logging.DEBUG, description="Create StripePaymentLinkPrice")
    
    def refresh():
        Log.new(logging_level=logging.INFO, description="Refresh StripePaymentLinkPrice")
        StripePaymentLinkPrice.objects.all().delete()
        for payment_link in StripePaymentLink.objects.all():
            for line_item in stripe.PaymentLink.list_line_items(payment_link.stripe_id).auto_paging_iter():
                stripe_id = line_item.price.id
                price = StripePrice.create_and_or_return(stripe_id=stripe_id)
                StripePaymentLinkPrice.objects.create(payment_link=payment_link, price=price)


class StripePrice(models.Model):
    """ A Stripe Price """
    stripe_id = models.CharField(max_length=64, help_text="What is the Stripe ID of this price?")
    name = models.CharField(max_length=64, help_text="What is the name of the Price?")
    interval = models.CharField(max_length=64, help_text="What is the interval type of this price?")
    price = models.IntegerField(help_text="What is the numerical base-currency value of this price?")
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
            api_record = StripePrice.fetch_api_data(stripe_id)
            api_prc = StripePrice.dict_from_api(api_record)
            product = StripeProduct.create_and_or_return(api_record.product)
            # print(product)
            price = StripePrice.objects.create(stripe_id=stripe_id, product=product, name=api_prc['name'], interval=api_prc['interval'], price=api_prc['price_amount'])
            Log.new(logging_level=logging.DEBUG, description="Create StripePrice", json=json)
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
            Log.new(logging_level=logging.DEBUG, description="Update StripePrice", json=json)
        else:
            StripePrice.objects.create(stripe_id=stripe_id, product=product, name=api_prc['name'], interval=api_prc['interval'], price=api_prc['price_amount'])
            Log.new(logging_level=logging.DEBUG, description="Create StripePrice", json=json)

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

    def refresh(new_only=False):
        """ clear out existing records and repopulate them from the API """
        Log.new(logging_level=logging.INFO, description="Refresh StripePrice")
        StripePrice.objects.all().delete()
        for price in stripe.Price.list(active=True).auto_paging_iter():
            # print(price.product)
            if stripe.Product.retrieve(price.product).active:
                product = StripeProduct.objects.get(stripe_id=price.product)
                api_prc = StripePrice.dict_from_api(price)
                StripePrice.objects.create(stripe_id=api_prc['stripe_id'], product=product, name=api_prc['name'], interval=api_prc['interval'], price=api_prc['price_amount'])
                Log.new(logging_level=logging.DEBUG, description="Create StripePrice", json={'stripe_id': api_prc['stripe_id']})


class StripeProduct(models.Model):
    """ A Stripe Product """
    stripe_id = models.CharField(max_length=64, help_text="What is the Stripe ID of this product?")
    name = models.CharField(max_length=64,  help_text="What is the name of this product?")
    description = models.TextField(max_length=512, help_text="What is the description of this product?")

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
            Log.new(logging_level=logging.DEBUG, description="Create StripeProduct", json=json)
        else:
            product = product_qs.first()
        
        return product

    def create_or_update(stripe_id):
        """ updates an existing record, otherwise creates one """
        json = {'stripe_id': stripe_id}
        
        product_qs = StripeProduct.objects.filter(stripe_id=stripe_id)
        api_prd = stripe.Product.retrieve(stripe_id)
        if product_qs.exists():
            product = product_qs.first()
            product.name = api_prd.name
            product.description = api_prd.description
            product.save()
            Log.new(logging_level=logging.DEBUG, description="Update StripeProduct", json=json)
        else:
            StripeProduct.objects.create(stripe_id=stripe_id, name=api_prd.name, description=api_prd.description)
            Log.new(logging_level=logging.DEBUG, description="Create StripeProduct", json=json)

    def get_url(self):
        """ URL for a hyperlink """
        return f"{ STRIPE_WWW_ENDPOINT }/products/{ self.stripe_id }"

    def refresh(new_only=False):
        """ clear out existing records and repopulate them from the API """
        Log.new(logging_level=logging.INFO, description="Refresh StripeProduct")
        StripeProduct.objects.all().delete()
        for product in stripe.Product.list(active=True).auto_paging_iter():
            StripeProduct.objects.create(stripe_id=product.id, name=product.name, description=product.description)
            Log.new(logging_level=logging.DEBUG, description="Create StripeProduct", json={'stripe_id': product.id})


class StripeSubscription(models.Model):
    """ A Stripe Subscription """
    stripe_id = models.CharField(max_length=64, help_text="What is the Stripe ID of this subscription?")
    customer = models.ForeignKey("subwaive.StripeCustomer", on_delete=models.CASCADE, help_text="What Stripe Customer holds this Subscription?")
    created = models.DateTimeField(null=True, blank=True, help_text="When was this subscription created?")
    current_period_end = models.DateTimeField(null=True, blank=True, help_text="When does this subscription end if not renewed?")
    status = models.CharField(max_length=64, help_text="What is the status of this subscription?")
    name = models.CharField(max_length=128, help_text="What is the name of this subscription?")

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
        created = fromtimestamp(api_record.created)
        current_period_end = fromtimestamp(api_record.current_period_end)
        status = api_record.status
        name = StripeSubscription.get_api_name(stripe_id)

        if subscription_qs.exists():
            if status == 'canceled':
                subscription_qs.delete()
                Log.new(logging_level=logging.INFO, description="Cancel StripeSubscription", json=json)
            else:
                subscription = subscription_qs.first()
                subscription.customer = StripeCustomer.create_and_or_return(customer_id)
                subscription.created = created
                subscription.current_period_end = current_period_end
                subscription.status = status
                subscription.name = name
                subscription.save()
    
                Log.new(logging_level=logging.DEBUG, description="Delete StripeSubscriptionItem", json={'subscription.id': subscription.id})
                StripeSubscriptionItem.objects.filter(subscription=subscription).delete()
                StripeSubscriptionItem.create_if_needed(api_record)
                Log.new(logging_level=logging.DEBUG, description="Update StripeSubscription", json=json)
        elif status != 'canceled':
            customer = StripeCustomer.create_and_or_return(customer_id)
            subscription = StripeSubscription.objects.create(stripe_id=stripe_id, customer=customer, name=name, created=created, current_period_end=current_period_end, status=status)
            Log.new(logging_level=logging.DEBUG, description="Delete StripeSubscriptionItem", json={'subscription.id': subscription.id})
            StripeSubscriptionItem.objects.filter(subscription=subscription).delete()
            StripeSubscriptionItem.create_if_needed(api_record)
            Log.new(logging_level=logging.DEBUG, description="Create StripeSubscription", json=json)

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

    def new(stripe_id, customer, name, created, current_period_end, status, subscription):
        """ create a new Stripe Subscription """
        StripeSubscription.objects.create(stripe_id=stripe_id, customer=customer, name=name, created=created, current_period_end=current_period_end, status=status)
        StripeSubscriptionItem.create_if_needed(subscription)
        Log.new(logging_level=logging.DEBUG, description="Create StripeSubscription", json={'stripe_id': stripe_id})

    def refresh(new_only=False):
        """ clear out existing records and repopulate them from the API """
        Log.new(logging_level=logging.INFO, description="Refresh StripeSubscription")
        StripeSubscription.objects.all().delete()
        for subscription in stripe.Subscription.search(query='-status:"canceled"').auto_paging_iter():
            customer = StripeCustomer.objects.get(stripe_id=subscription.customer)

            stripe_id = subscription['id']
            name = StripeSubscription.get_api_name(stripe_id)

            created = fromtimestamp(subscription.created)
            current_period_end = fromtimestamp(subscription.current_period_end)
            status = subscription.status

            subscription_qs = StripeSubscription.objects.filter(stripe_id=stripe_id)
            if subscription_qs:
                subscription_qs.first().update(created, current_period_end, status)
            else:
                StripeSubscription.new(stripe_id, customer, name, created, current_period_end, status, subscription)

    def update(self, created, current_period_end, status):
        """ Update an existing Stripe subscription """
        is_update = False
        json = {'stripe_id': self.stripe_id}

        if created != self.created:
            # how can creation date be updated?
            is_update = True
            json['created_old'] = self.created
            self.created = created

        if current_period_end != self.current_period_end:
            is_update = True
            json['current_period_end_old'] = self.current_period_end
            self.current_period_end = current_period_end
        
        if status != self.status:
            is_update = True
            json['status_old'] = self.status
            self.status = status

        if is_update:
            self.save()
            Log.new(logging_level=logging.DEBUG, description="Update StripeSubscription", json=json)


class StripeSubscriptionItem(models.Model):
    """ A Stripe SubscriptionItem """
    stripe_id = models.CharField(max_length=64, help_text="What is the Stripe ID of this subscription item?")
    subscription = models.ForeignKey("subwaive.StripeSubscription", on_delete=models.CASCADE, help_text="What subscription is this subscription item a part of?")
    price = models.ForeignKey("subwaive.StripePrice", on_delete=models.CASCADE, help_text="What Stripe Price is associated with the subscription item?")

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
                Log.new(logging_level=logging.DEBUG, description="Create StripeSubscriptionItem")

