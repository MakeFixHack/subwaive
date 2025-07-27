import datetime

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse

from subwaive.models import DocusealFieldStore, StripeCustomer
from subwaive.models import Event
from subwaive.models import Person, PersonEmail, PersonEvent
from subwaive.utils import CONFIDENTIALITY_LEVEL_CONFIDENTIAL


@login_required
def person_list(request):
    """ List of people in the system """
    persons_prelim = Person.objects.all().order_by('name','preferred_email__email')

    persons = [
        {
            'name': p.name,
            'id': p.id,
            'person_card': redirect('person_card', person_id=p.id).url,
            'last_check_in': p.get_last_check_in(),
            'membership_status': p.check_membership_status(),
            'last_check_in_event_id_list': [ci.event.id for ci in PersonEvent.objects.filter(person=p, event__start__date=datetime.date.today())],
        }
        for p in persons_prelim
    ]

    check_in_events = Event.get_current_event()

    button_dict = [
            {'url': reverse('person_list'), 'anchor': 'All', 'active': True},
            {'url': reverse('member_list'), 'anchor': 'Members'},
            {'url': reverse('member_email_list'), 'anchor': 'Email'},
            {'url': reverse('person_search'), 'anchor': 'Search'},
    ]

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_CONFIDENTIAL,
        'persons': persons,
        'buttons': button_dict,
        'check_in_events': check_in_events,
    }

    return render(request, f'subwaive/person/person-list.html', context)


@login_required
def member_list(request):
    """ List of members in the system """
    persons_prelim = Person.objects.all().order_by('name','preferred_email__email')

    persons = [
        {
            'name': p.name,
            'id': p.id,
            'person_card': redirect('person_card', person_id=p.id).url,
            'last_check_in': p.get_last_check_in(),
            'membership_status': p.check_membership_status(),
            'last_check_in_event_id_list': [ci.event.id for ci in PersonEvent.objects.filter(person=p, event__start__date=datetime.date.today())],
        }
        for p in persons_prelim if p.check_membership_status()
    ]

    check_in_events = Event.get_current_event()

    button_dict = [
            {'url': reverse('person_list'), 'anchor': 'All'},
            {'url': reverse('member_list'), 'anchor': 'Members', 'active': True},
            {'url': reverse('member_email_list'), 'anchor': 'Email'},
            {'url': reverse('person_search'), 'anchor': 'Search'},
    ]

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_CONFIDENTIAL,
        'persons': persons,
        'buttons': button_dict,
        'check_in_events': check_in_events,
    }

    return render(request, f'subwaive/person/person-list.html', context)


@login_required
def member_email_list(request):
    """ Return a list of preferred emails for current members """
    persons_prelim = Person.objects.all().order_by('name','preferred_email__email')

    persons = [
        {
            'name': p.name,
            'preferred_email': p.preferred_email
        }
        for p in persons_prelim if p.check_membership_status()
    ]

    check_in_events = Event.get_current_event()

    button_dict = [
            {'url': reverse('person_list'), 'anchor': 'All'},
            {'url': reverse('member_list'), 'anchor': 'Members'},
            {'url': reverse('member_email_list'), 'anchor': 'Email', 'active': True},
            {'url': reverse('person_search'), 'anchor': 'Search'},
    ]

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_CONFIDENTIAL,
        'persons': persons,
        'buttons': button_dict,
        'check_in_events': check_in_events,
    }

    return render(request, f'subwaive/person/person-email.html', context)


@login_required
def person_search(request):
    """ Search for people by name or email """
    search_term = request.POST.get('search_term', None)

    results_prelim = None
    results = None
    if search_term:
        results_prelim = Person.search(search_term)

    if results_prelim:
        if len(results_prelim) == 1:
            return redirect('person_card', results_prelim.first().id)
        else:
            results = [
                {
                    'name': p.name,
                    'id': p.id,
                    'person_card': redirect('person_card', person_id=p.id).url,
                    'preferred_email': p.preferred_email.email,
                    'membership_status': p.check_membership_status(),
                    'last_check_in': p.get_last_check_in(),
                    'last_check_in_event_id_list': [ci.event.id for ci in PersonEvent.objects.filter(person=p, event__start__date=datetime.date.today())],
                }
                for p in results_prelim
            ]

    check_in_events = Event.get_current_event()
       
    button_dict = [
            {'url': reverse('person_list'), 'anchor': 'List'},
            {'url': reverse('member_list'), 'anchor': 'Members'},
            {'url': reverse('member_email_list'), 'anchor': 'Email'},
            {'url': reverse('person_search'), 'anchor': 'Search', 'active': True},
    ]

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_CONFIDENTIAL,
        'search_term': search_term,
        'results': results,
        'buttons': button_dict,
        'check_in_events': check_in_events,
    }

    return render(request, f'subwaive/person/person-search.html', context)

@login_required
def person_card(request, person_id):
    """ A page with info and links related to an individual """
    person = Person.objects.get(id=person_id)
    other_emails = PersonEmail.objects.filter(person=person)
    
    has_waiver = person.check_waiver_status()
    membership_status = person.check_membership_status()
    memberships = person.get_memberships()
    
    last_check_ins = PersonEvent.objects.filter(person=person).order_by('-event__end')[:5]
    check_in_events = Event.get_current_event()

    button_dict = [
        {'url': reverse('person_docuseal', kwargs={'person_id': person.id }), 'anchor': 'Docuseal', 'class': 'secondary', 'active': False},
        {'url': reverse('person_stripe', kwargs={'person_id': person.id }), 'anchor': 'Stripe', 'class': 'secondary', 'active': False},
        {'url': reverse('person_card', kwargs={'person_id': person.id }), 'anchor': 'View', 'class': 'info', 'active': True },
        {'url': reverse('person_edit', kwargs={'person_id': person.id }), 'anchor': 'Edit', 'class': 'success', 'active': False },
    ]        

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_CONFIDENTIAL,
        'buttons': button_dict,
        'person': person,
        'other_emails': other_emails,
        'has_waiver': has_waiver,
        'membership_status': membership_status,
        'memberships': memberships,
        'last_check_ins': last_check_ins,
        'last_check_in_event_id_list': [ci.event.id for ci in last_check_ins],
        'check_in_events': check_in_events,
    }

    return render(request, f'subwaive/person/person-card.html', context)

@login_required
def person_docuseal(request, person_id):
    """ A page with info and links related to an individual """
    person = Person.objects.get(id=person_id)

    button_dict = [
        {'url': reverse('person_docuseal', kwargs={'person_id': person.id }), 'anchor': 'Docuseal', 'class': 'info', 'active': True},
        {'url': reverse('person_stripe', kwargs={'person_id': person.id }), 'anchor': 'Stripe', 'class': 'secondary', 'active': False},
        {'url': reverse('person_card', kwargs={'person_id': person.id }), 'anchor': 'View', 'class': 'secondary', 'active': False },
        {'url': reverse('person_edit', kwargs={'person_id': person.id }), 'anchor': 'Edit', 'class': 'success', 'active': False },
    ]        

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_CONFIDENTIAL,
        'buttons': button_dict,
        'person': person,
        'archived_documents': person.get_documents("archived"),
        'pending_documents': person.get_documents("pending"),
        'current_documents': person.get_documents("current"),
    }

    return render(request, f'subwaive/person/person-docuseal.html', context)

@login_required
def person_stripe(request, person_id):
    """ A page with info and links related to an individual """
    person = Person.objects.get(id=person_id)

    button_dict = [
        {'url': reverse('person_docuseal', kwargs={'person_id': person.id }), 'anchor': 'Docuseal', 'class': 'secondary', 'active': False},
        {'url': reverse('person_stripe', kwargs={'person_id': person.id }), 'anchor': 'Stripe', 'class': 'info', 'active': True},
        {'url': reverse('person_card', kwargs={'person_id': person.id }), 'anchor': 'View', 'class': 'secondary', 'active': False },
        {'url': reverse('person_edit', kwargs={'person_id': person.id }), 'anchor': 'Edit', 'class': 'success', 'active': False },
    ]        

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_CONFIDENTIAL,
        'buttons': button_dict,
        'person': person,
        'stripe_subscriptions': person.get_memberships(),
        'stripe_onetime_payments': person.get_day_passes(),
        'stripe_events': person.get_events(),
        'stripe_donor_status': person.get_donor_status(),
    }

    return render(request, f'subwaive/person/person-stripe.html', context)

@login_required
def person_edit(request, person_id):
    """ a page to edit a person's record """
    person = Person.objects.get(id=person_id)
    other_emails = PersonEmail.objects.filter(person=person)
    submissions = person.get_submissions("current")
    important_fields = DocusealFieldStore.objects.filter(submission__in=submissions, field__field__icontains='name')
    stripe_customers = StripeCustomer.objects.filter(email__in=[e.email for e in other_emails]).order_by('name')

    last_check_ins = PersonEvent.objects.filter(person=person).order_by('-event__end')[:5]
    
    button_dict = [
        {'url': reverse('person_docuseal', kwargs={'person_id': person.id }), 'anchor': 'Docuseal', 'active': False},
        {'url': reverse('person_stripe', kwargs={'person_id': person.id }), 'anchor': 'Stripe', 'active': False},
        {'url': reverse('person_card', kwargs={'person_id': person.id }), 'anchor': 'View', 'active': False },
        {'url': reverse('person_edit', kwargs={'person_id': person.id }), 'anchor': 'Edit', 'class': 'success', 'active': True },
    ]        

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_CONFIDENTIAL,
        'buttons': button_dict,
        'person': person,
        'important_fields': important_fields,
        'stripe_customers': stripe_customers,
        'last_check_ins': last_check_ins,
        'other_emails': other_emails,
    }

    return render(request, f'subwaive/person/person-edit.html', context)

@login_required
def merge_people(request, merge_child_id, merge_parent_id=None):
    """ a page for merging people """
    merge_child = Person.objects.get(id=merge_child_id)
    name = merge_child.name

    if merge_parent_id:
        merge_parent = Person.objects.get(id=merge_parent_id)
        merge_parent.merge(merge_child_id)
        return_object = redirect('person_card', merge_parent_id)
    
        messages.success(request, f'<em>{ name }</em> merged')

    else:       
        merge_child = {
            'id': merge_child.id,
            'name': merge_child.name,
            'emails': merge_child.get_email_list(),
            } 
        
        persons = Person.objects.exclude(id=merge_child_id)

        merge_parents = [
            {
                'id': p.id,
                'name': p.name,
                'emails': p.get_email_list(),
                } 
            for p in persons
            ]

        context = {
            'merge_parents': merge_parents,
            'merge_child': merge_child,
            'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_CONFIDENTIAL,
        }

        return_object = render(request, f'subwaive/person/person-merge.html', context)
    
    return return_object

@login_required
def unmerge_people(request, email_id):
    """ unmerge people """
    merge_parent = PersonEmail.objects.get(id=email_id)
    email = merge_parent.email
    merge_parent.unmerge()

    merge_child = Person.search(email)[0]

    messages.success(request, f'<em>{ email }</em> unmerged')

    return redirect('person_edit', merge_child.id)

@login_required
def set_preferred_email(request, email_id):
    """ set the preferred email for a person """
    email = PersonEmail.objects.get(id=email_id)
    person = email.person
    person.preferred_email = email
    person.save()

    messages.success(request, f'<em>{ email }</em> set as preferred')

    return redirect('person_edit', person.id)

@login_required
def set_docuseal_name(request, person_id, important_field_id):
    """ set the person name to a Docuseal important field value """
    person = Person.objects.get(id=person_id)
    name = DocusealFieldStore.objects.get(id=important_field_id).value
    person.name = name
    person.save()

    messages.success(request, f'Name set to <em>{ name }</em>')

    return redirect('person_edit', person_id)

@login_required
def set_stripe_name(request, person_id, customer_id):
    """ set the person name to a Stripe customer name """
    person = Person.objects.get(id=person_id)
    name = StripeCustomer.objects.get(id=customer_id).name
    person.name = name
    person.save()

    messages.success(request, f'Name set to <em>{ name }</em>')

    return redirect('person_edit', person_id)
