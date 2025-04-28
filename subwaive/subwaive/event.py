import datetime
import os
import pytz

from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from subwaive.models import CalendarEvent, Event
from subwaive.models import Person, PersonEvent
from subwaive.utils import refresh, CONFIDENTIALITY_LEVEL_PUBLIC, CONFIDENTIALITY_LEVEL_CONFIDENTIAL

TIME_ZONE = os.environ.get("TIME_ZONE")
CALENDAR_URL = os.environ.get("CALENDAR_URL")

DATA_REFRESH_TOKEN = os.environ.get("DATA_REFRESH_TOKEN")

PAGINATOR_SHORT = 8

@login_required
def member_check_in(request, person_id, event_id, override_checks=False):
    """ A method logging a member was in the space. """
    waiver_check = Person.check_waiver_status_by_person_id(person_id)
    # print(waiver_check)
    membership_status = Person.check_membership_status_by_person_id(person_id)
    print(membership_status)
    has_prior_check_in = PersonEvent.check_prior_check_in(person_id, event_id)
    print(has_prior_check_in)

    clean_checks = False
    if override_checks:
        clean_checks = True
    elif waiver_check and membership_status=='active' and not has_prior_check_in:
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
def delete_member_check_in(request, person_id, event_id):
    """ A method for removing erroneous check-ins """
    check_in = PersonEvent.objects.get(person__id=person_id, event__id=event_id)
    
    messages.success(request, f"Check-in for { check_in.person } to {check_in.event } removed")

    check_in.delete()

    return redirect('event_details', event_id)

@login_required
def event_refresh_page(request):
    """ a page for initiating ical Event data refreshes """
    page_title = 'Event Data'
    data_source = CALENDAR_URL

    tiles = [
        {
            'buttons': [
                {'url_name': 'refresh_event', 'post': [
                    {
                        'type': 'hidden',
                        'name': 'lbound',
                        'val': datetime.date.today().isoformat()
                    },
                    {
                        'type': 'datepicker',
                        'label': 'Events between today and...',
                        'name': 'ubound',
                        'val': (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
                    },
                ], 'anchor': 'Refresh Upcoming'},
            ],
            'log_descriptions': [
                {'description': 'Event'},
            ]
        },
    ]

    return refresh(request, page_title, data_source, tiles)

@login_required
def refresh_event(request):
    """ force refresh ical Event data """
    CalendarEvent.refresh(request)

    messages.success(request, f'Event data refreshed')

    return redirect('event_refresh')

@csrf_exempt
def refresh_event_by_token(request):
    """ allow event data refresh by token """

    if request.headers.get('X-Refresh-Token') == DATA_REFRESH_TOKEN:
        print(datetime.datetime.now(), "Refreshing events by token")
        CalendarEvent.refresh(request)

        return HttpResponse(status=200)
    else:
        return HttpResponse(status=401)

@login_required
def event_list(request, timeframe="past"):
    """ List of events """
    if timeframe == "past":
        events = CalendarEvent.objects.filter(start__lte=datetime.datetime.now().astimezone(pytz.timezone(TIME_ZONE))).order_by('-end')
    elif timeframe == "future":
        events = CalendarEvent.objects.filter(start__gt=datetime.datetime.now().astimezone(pytz.timezone(TIME_ZONE))).order_by('start')
    else:
        events = CalendarEvent.objects.all().order_by('-end')
    events = events.annotate(attendee_count=Count('attendee'))
    
    paginator = Paginator(events, PAGINATOR_SHORT)
    page_number = request.GET.get('page')
    events = paginator.get_page(page_number)

    button_dict = [
            {'url': reverse('event_list'), 'anchor': 'Past', 'active': timeframe=="past"},
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
        membership_status = p.check_membership_status()
        if not membership_status:
            issues['membership'] = 'missing'
        elif membership_status!='active':
            issues['membership'] = 'inactive'
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

@login_required
def event_refresh(request, event_id):
    """ refresh an individual event """
    print("entered event_refresh")
    Event.objects.get(id=event_id).refresh_event()

    return redirect('event_details', event_id)
