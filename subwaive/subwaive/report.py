import datetime

from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render

from subwaive.models import DocusealTemplate,PersonEvent

"""
Trends
"""

@login_required
def recent_member_activity(request, lag_days=60):
    """ Event attendance totals and by day-of-week """
    excludes = ['MakeFixHack-Volunteer-Agreement','Director-Independence-Questionnaire','MakeFixHack-Conflict-of-interest-Policy']

    cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=lag_days)).date()
    pe = PersonEvent.objects.filter(event__start__date__gte=cutoff_date)

    attendees = {}
    for p in pe:
        is_exclude = False
        for d in DocusealTemplate.objects.filter(docusealsubmission__docusealsubmittersubmission__submitter__persondocuseal__person=p.person):
            if any(x in d.name for x in excludes):
                is_exclude = True
            if not is_exclude:
                person_name = p.person.name
                if person_name not in attendees.keys():
                    attendees[person_name] = {}
                event_dow = p.event.start.date().weekday()
                if event_dow in attendees[person_name].keys():
                    attendees[person_name][p.event.start.date().weekday()] += 1
                else:
                    attendees[person_name][p.event.start.date().weekday()] = 1

    days = ['Monday', 'Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    
    totals = []
    for a,c in attendees.items():
        t = sum([v for k,v in c.items()])
        totals.append((a,t))

    grid = []
    for a,c in attendees.items():
        line = [a]
        for d in range(7):
            if d in c.keys():
                line.append(c[d])
            else:
                line.append('')
        grid.append(line)

    dow = {days[d]:0 for d in range(7)}
    for a,c in attendees.items():
        for d in range(7):
            if d in c.keys():
                dow[days[d]] += c[d]
    
    context = {
        'attendees': attendees,
        'totals': totals,
        'grid': grid,
        'dow': dow,
        'days': days,
        }

    return render(request, f'subwaive/reports/recent-member-activity.html', context)
