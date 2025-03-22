import datetime
import os
import pytz

from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import render, redirect
from django.urls import reverse

from subwaive.docuseal import check_waiver_status
from subwaive.models import DocusealFieldStore
from subwaive.models import Log, Person, PersonEmail, QRCustom
from subwaive.stripe import check_membership_status
from subwaive.utils import generate_qr_svg, CONFIDENTIALITY_LEVEL_PUBLIC, CONFIDENTIALITY_LEVEL_HIGH, QR_SMALL, QR_LARGE

@permission_required('subwaive.can_list_customers')
@login_required
def person_list(request):
    """ List of people in the system """
    persons_prelim = Person.objects.all().order_by('name','preferred_email__email')

    persons = [
        {
            'name': p.name,
            'id': p.id,
            'person_card': redirect('person_card', person_id=p.id).url,
            'preferred_email': p.preferred_email.email,
        }
        for p in persons_prelim
    ]

    for p in persons:
        last_check_in = get_last_check_in(p['id'])
        if last_check_in:
            p['last_check_in'] = last_check_in.date()
        else:
            p['last_check_in'] = None
        p['has_membership'] = check_membership_status(p['id'])

    button_dict = [
            {'url': reverse('person_list'), 'anchor': 'List', 'active': True},
            {'url': reverse('person_search'), 'anchor': 'Search'},
    ]

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_HIGH,
        'persons': persons,
        'buttons': button_dict,
    }

    return render(request, f'subwaive/person/person-list.html', context)

@login_required
def custom_link_list(request):
    """ Build a list of links to QR codes """
    user_qr_codes = QRCustom.objects.all().order_by('category','name')

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

    context = {
        'page_title': 'Links',
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_PUBLIC,
        'categories': categories,
        'qr_list': user_qr_list,
    }

    return render(request, f'subwaive/qr-links.html', context)

@login_required
@permission_required('subwaive.can_search_customers')
def person_search(request):
    """ Search for customers by name or email """
    search_term = request.POST.get('search_term', None)

    results = None
    if search_term:
        results = Person.search(search_term)

    button_dict = [
            {'url': reverse('person_list'), 'anchor': 'List'},
            {'url': reverse('person_search'), 'anchor': 'Search', 'active': True},
    ]

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_HIGH,
        'search_term': search_term,
        'results': results,
        'buttons': button_dict,
    }

    return render(request, f'subwaive/person/person-search.html', context)

@login_required
def person_card(request, person_id):
    """ A page with info and links related to an individual """
    person = Person.objects.get(id=person_id)
    other_emails = PersonEmail.objects.filter(person=person)
    
    has_waiver = check_waiver_status(person_id)
    has_membership = person.check_membership_status()
    
    last_check_in_prelim = get_last_check_in(person_id)
    last_check_in = None
    if last_check_in_prelim:
        last_check_in = {
                'event': last_check_in_prelim.json['event'],
                'date': last_check_in_prelim.date()
            }

    important_fields = DocusealFieldStore.objects.filter(submission__in=person.get_submissions())

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_HIGH,
        'person': person,
        'other_emails': other_emails,
        'has_waiver': has_waiver,
        'has_membership': has_membership,
        'last_check_in': last_check_in,
        'important_fields': important_fields,
    }

    return render(request, f'subwaive/person/person-card.html', context)

@login_required
def person_docuseal(request, person_id):
    """ A page with info and links related to an individual """
    person = Person.objects.get(id=person_id)

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_HIGH,
        'person': person,
        'docuseal_documents': person.get_documents(),
    }

    return render(request, f'subwaive/person/person-docuseal.html', context)

@login_required
def person_stripe(request, person_id):
    """ A page with info and links related to an individual """
    person = Person.objects.get(id=person_id)

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_HIGH,
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
    submissions = person.get_submissions()
    important_fields = DocusealFieldStore.objects.filter(submission__in=submissions, field__field__icontains='name')

    check_in_prelim = Log.objects.filter(json__person_id=person_id,description="Check-in")[:5]
    check_ins = [
        {
            'id': c.id,
            'event': c.json['event'],
            'date': c.date()
        }
        for c in check_in_prelim
    ]
    
    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_HIGH,
        'person': person,
        'important_fields': important_fields,
        'check_ins': check_ins,
        'other_emails': other_emails,
    }

    return render(request, f'subwaive/person/person-edit.html', context)

def get_last_check_in(person_id):
    """ return a Log for the last time a person checked in """
    return Log.get_last(description='Check-in', json={'person_id': person_id})

def check_prior_check_in(person_id):
    """ check if a person has already been checked in today """
    last_check_in = get_last_check_in(person_id)
    is_checked_in = False
    if last_check_in:
        if last_check_in.date() == datetime.date.today():
            is_checked_in = True
    return is_checked_in

@login_required
def member_check_in(request, person_id, override_checks=False):
    """ A method logging a member was in the space. """
    waiver_check = check_waiver_status(person_id)
    print(waiver_check)
    membership_status = check_membership_status(person_id)
    print(membership_status)
    has_prior_check_in = check_prior_check_in(person_id)
    print(has_prior_check_in)

    clean_checks = False
    if override_checks:
        clean_checks = True
    elif waiver_check and membership_status and not has_prior_check_in:
        clean_checks = True

    if clean_checks:
        check_results = {'waiver_check': waiver_check, 'membership_status': membership_status, 'has_prior_check_in': has_prior_check_in, 'override_checks': override_checks}
        payload = {'person_id': person_id, 'check_in_by': request.user.username, 'check_results': check_results, 'event': get_event()}
        Log.objects.create(description="Check-in", json=payload)
        print('checked-in')
        return redirect('person_card', person_id)
    else:
        print('check-in checks failed')
        return check_in_remediation(request=request, person_id=person_id, waiver_check=waiver_check, membership_status=membership_status, has_prior_check_in=has_prior_check_in)

@login_required
def force_member_check_in(request, person_id):
    """ force a member check-in in spite of failed checks """
    return member_check_in(request=request, person_id=person_id, override_checks=True)

@login_required
def check_in_remediation(request, person_id, waiver_check, membership_status, has_prior_check_in):
    """ A person failed one or more checks for check-in, provide details on how to clear the checks """
    person = Person.objects.get(id=person_id)

    context = {
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_HIGH,
        'person': person,
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

def get_event():
    """ return the name of the current event from the RSS calendar feed """
    #!!! need to link calendar
    return "Unknown event"

@login_required
def merge_people(request, merge_child_id, merge_parent_id=None):
    """ a page for merging people """
    if merge_parent_id:
        merge_parent = Person.objects.get(id=merge_parent_id)
        merge_parent.merge(merge_child_id)
        return_object = redirect('person_card', merge_parent_id)

    else:
        person = Person.objects.get(id=merge_child_id)
        
        merge_child = {
            'id': person.id,
            'name': person.name,
            'emails': person.get_email_list(),
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
            'CONFIDENTIALITY_LEVEL_HIGH': CONFIDENTIALITY_LEVEL_HIGH,
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

    return redirect('person_edit', merge_child.id)

@login_required
def set_preferred_email(request, email_id):
    """ set the preferred email for a person """
    email = PersonEmail.objects.get(id=email_id)
    person = email.person
    person.preferred_email = email
    person.save()

    return redirect('person_edit', person.id)

@login_required
def set_name(request, person_id, important_field_id):
    """ set the person name to a Docuseal important field value """
    person = Person.objects.get(id=person_id)
    name = DocusealFieldStore.objects.get(id=important_field_id).value
    person.name = name
    person.save()

    return redirect('person_edit', person_id)
