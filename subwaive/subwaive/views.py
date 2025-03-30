import datetime
import os
import pytz

from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import render, redirect
from django.urls import reverse

from subwaive.models import DocusealFieldStore
from subwaive.models import Event, PersonEvent
from subwaive.models import Log, Person, PersonEmail, QRCustom
from subwaive.utils import generate_qr_svg, refresh, CONFIDENTIALITY_LEVEL_PUBLIC, CONFIDENTIALITY_LEVEL_SENSITIVE, CONFIDENTIALITY_LEVEL_CONFIDENTIAL, QR_SMALL, QR_LARGE

CALENDAR_URL = os.environ.get("CALENDAR_URL")

@permission_required('subwaive.can_list_people')
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
            'has_membership': p.check_membership_status(),
            'last_check_in_event_id_list': [ci.event.id for ci in PersonEvent.objects.filter(person=p, event__start__date=datetime.date.today())],
        }
        for p in persons_prelim
    ]

    check_in_events = Event.get_current_event()

    button_dict = [
            {'url': reverse('person_list'), 'anchor': 'List', 'active': True},
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
def public_link_list(request):
    return custom_link_list(request, is_sensitive=False)

@login_required
def sensitive_link_list(request):
    return custom_link_list(request, is_sensitive=True)

@login_required
def custom_link_list(request, is_sensitive=False):
    """ Build a list of links to QR codes """
    user_qr_codes = QRCustom.objects.filter(category__is_sensitive=is_sensitive).order_by('category','name')

    user_qr_list = [
        {
            'id' : qr.id,
            'category': qr.category.name,
            'name': qr.name,
            'svg_small': generate_qr_svg(qr.content, QR_SMALL),
            'svg_large': generate_qr_svg(qr.content,QR_LARGE ),
            'url': qr.content if 'https' in qr.content else None
        }
        for qr in user_qr_codes
    ]

    categories = [
        {
            'name': category[0],
            'baseid': f'cat-{ category[1] }',
        }
        for category in set([(c.category.name, c.category.id) for c in user_qr_codes])
    ]
    categories = sorted(categories, key=lambda x: x['name'])

    if is_sensitive:
        confidentiality_level = CONFIDENTIALITY_LEVEL_SENSITIVE
    else:
        confidentiality_level = CONFIDENTIALITY_LEVEL_PUBLIC

    context = {
        'page_title': 'Links',
        'CONFIDENTIALITY_LEVEL': confidentiality_level,
        'categories': categories,
        'qr_list': user_qr_list,
    }

    return render(request, f'subwaive/qr-links.html', context)

@login_required
@permission_required('subwaive.can_search_people')
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
                    'last_check_in': p.get_last_check_in(),
                    'last_check_in_event_id_list': [ci.event.id for ci in PersonEvent.objects.filter(person=p, event__start__date=datetime.date.today())],
                }
                for p in results_prelim
            ]

    check_in_events = Event.get_current_event()
       
    button_dict = [
            {'url': reverse('person_list'), 'anchor': 'List'},
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
    has_membership = person.check_membership_status()
    
    last_check_ins = PersonEvent.objects.filter(person=person).order_by('-event__end')[:5]
    check_in_events = Event.get_current_event()

    button_dict = [
        {'url': reverse('person_docuseal', kwargs={'person_id': person.id }), 'anchor': 'Docuseal', 'class': 'info', 'active': True},
        {'url': reverse('person_stripe', kwargs={'person_id': person.id }), 'anchor': 'Stripe', 'class': 'info', 'active': True},
        {'url': reverse('person_edit', kwargs={'person_id': person.id }), 'anchor': 'Edit', 'class': 'success', 'active': True },
    ]        

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_CONFIDENTIAL,
        'buttons': button_dict,
        'person': person,
        'other_emails': other_emails,
        'has_waiver': has_waiver,
        'has_membership': has_membership,
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
        {'url': reverse('person_card', kwargs={'person_id': person.id }), 'anchor': 'View Card', 'class': 'info', 'active': True},
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
        {'url': reverse('person_card', kwargs={'person_id': person.id }), 'anchor': 'View Card', 'class': 'info', 'active': True},
    ]        

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_CONFIDENTIAL,
        'buttons': button_dict,
        'person': person,
        'stripe_subscriptions': person.get_memberships(),
        'stripe_onetime_payments': person.get_day_passes(),
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

    last_check_ins = PersonEvent.objects.filter(person=person).order_by('-event__end')[:5]
    
    button_dict = [
        {'url': reverse('person_card', kwargs={'person_id': person.id }), 'anchor': 'View Card', 'class': 'info', 'active': True},
    ]        

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_CONFIDENTIAL,
        'buttons': button_dict,
        'person': person,
        'important_fields': important_fields,
        'last_check_ins': last_check_ins,
        'other_emails': other_emails,
    }

    return render(request, f'subwaive/person/person-edit.html', context)

@login_required
def member_check_in(request, person_id, event_id, override_checks=False):
    """ A method logging a member was in the space. """
    waiver_check = Person.check_waiver_status_by_person_id(person_id)
    # print(waiver_check)
    membership_status = Person.check_membership_status(person_id)
    print(membership_status)
    has_prior_check_in = PersonEvent.check_prior_check_in(person_id, event_id)
    print(has_prior_check_in)

    clean_checks = False
    if override_checks:
        clean_checks = True
    elif waiver_check and membership_status and not has_prior_check_in:
        clean_checks = True

    if clean_checks:
        check_results = {'waiver_check': waiver_check, 'membership_status': membership_status, 'has_prior_check_in': has_prior_check_in, 'override_checks': override_checks}
        check_in = Person.objects.get(id=person_id).check_in(event_id)
        messages.success(request, f"Checked-in for { check_in.event.summary }")

        return redirect('person_card', person_id)
    else:
        print('check-in checks failed')
        return check_in_remediation(request=request, person_id=person_id, event_id=event_id, waiver_check=waiver_check, membership_status=membership_status, has_prior_check_in=has_prior_check_in)

@login_required
def force_member_check_in(request, person_id, event_id):
    """ force a member check-in in spite of failed checks """
    return member_check_in(request=request, person_id=person_id, event_id=event_id, override_checks=True)

@login_required
def check_in_remediation(request, person_id, event_id, waiver_check, membership_status, has_prior_check_in):
    """ A person failed one or more checks for check-in, provide details on how to clear the checks """
    person = Person.objects.get(id=person_id)
    event = Event.objects.get(id=event_id)

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_CONFIDENTIAL,
        'person': person,
        'event': event,
        'waiver_check': waiver_check,
        'membership_status': membership_status,
        'has_prior_check_in': has_prior_check_in,
    }

    return render(request, f'subwaive/person/person-remediation.html', context)

@permission_required('subwaive.can_remove_check_in')
@login_required
def delete_member_check_in(request, log_id):
    """ A method for removing erroneous check-ins """
    log = Log.objects.get(id=log_id)
    person_id = log.json['person_id']

    log.description = f"DELETED - { log.description }"
    log.json['deleted_by'] = request.user.username
    log.json['deleted_on'] = datetime.datetime.now().astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')
    log.save()

    return redirect('person_edit', person_id)

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
def set_name(request, person_id, important_field_id):
    """ set the person name to a Docuseal important field value """
    person = Person.objects.get(id=person_id)
    name = DocusealFieldStore.objects.get(id=important_field_id).value
    person.name = name
    person.save()

    messages.success(request, f'Name set to <em>{ name }</em>')

    return redirect('person_edit', person_id)

@login_required
def event_refresh_page(request):
    """ a page for initiating ical Event data refreshes """
    log_descriptions = [
        "Refresh Event",
    ]

    description = CALENDAR_URL

    button_dict = [
            {'url_name': 'refresh_event', 'anchor': 'Refresh Events'},
    ]

    return refresh(request, log_descriptions, button_dict, description)

@login_required
def refresh_event(request):
    """ force refresh ical Event data """
    webhook_refresh()

    messages.success(request, f'Event data refreshed')

    return redirect('event_refresh')

def webhook_refresh():
    """ refresh data sets in order """
    Event.refresh()

@login_required
def event_list(request, timeframe="last-five"):
    """ List of events """
    if timeframe == "last-five":
        events = Event.objects.filter(start__lte=datetime.date.today()).order_by('-end')[:5]
    elif timeframe == "future":
        events = Event.objects.filter(start__gt=datetime.date.today()).order_by('start')
    elif timeframe == "all":
        events = Event.objects.all().order_by('-end')

    button_dict = [
            {'url': reverse('event_list'), 'anchor': 'Last 5', 'active': timeframe=="last-five"},
            {'url': reverse('event_list', kwargs={'timeframe': 'future' }), 'anchor': 'Future', 'active': timeframe=="future"},
            {'url': reverse('event_list', kwargs={'timeframe': 'all' }), 'anchor': 'All', 'active': timeframe=="all"},
    ]

    context = {
        'events': events,
        'buttons': button_dict,
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_PUBLIC,
    }

    return render(request, f'subwaive/event/event-list.html', context)

@login_required
def event_details(request, event_id):
    """ Details of events """
    event = Event.objects.get(id=event_id)

    if request.POST:
        person = Person.objects.get(id=request.POST.get("person_id"))
        PersonEvent.objects.create(event=event, person=person)
        return redirect('event_details', event_id)

    persons = [p.person for p in PersonEvent.objects.filter(event=event).order_by('person__name')]

    check_in_issues = []
    for p in persons:
        issues = {}
        if not p.check_membership_status():
            issues['membership'] = True
        if not p.check_waiver_status():
            issues['waiver'] = True
        if issues.keys():
            issues['person'] = p
            check_in_issues.append(issues)

    possible_check_ins = Person.objects.exclude(id__in=[p.id for p in persons])

    context = {
        'event': event,
        'persons': persons,
        'possible_check_ins': possible_check_ins,
        'check_in_issues': check_in_issues,
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_CONFIDENTIAL,
    }

    return render(request, f'subwaive/event/event-details.html', context)