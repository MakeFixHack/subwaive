import json
import os

from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse

from subwaive.models import PersonDocuseal,Log
from subwaive.models import DocusealFieldStore, DocusealSubmission, DocusealSubmitter, DocusealSubmitterSubmission, DocusealTemplate
from subwaive.utils import generate_qr_svg, refresh, CONFIDENTIALITY_LEVEL_PUBLIC, QR_SMALL, QR_LARGE

DOCUSEAL_API_ENDPOINT = os.environ.get("DOCUSEAL_API_ENDPOINT")

@login_required
def qr_links(request):
    """ Build a list of links with QR codes """
    templates = DocusealTemplate.objects.all()

    template_list = [
        {
            'id' : t.id,
            'category': t.folder_name,
            'name': t.name,
            'url': f"{ t.get_url() }",
            'svg_small': generate_qr_svg(f"{ t.get_url() }", QR_SMALL),
            'svg_large': generate_qr_svg(f"{ t.get_url() }", QR_LARGE),
        }
        for t in templates
    ]

    categories = [
        {
            'name': folder_name,
            'baseid': f"cat-{ idx }",
        }
        for idx,folder_name in enumerate(set([t.folder_name for t in templates]))
    ]

    context = {
        'page_title': 'Links - Docuseal',
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_PUBLIC,
        'qr_list': template_list,
        'categories': categories,
    }

    return render(request, f'subwaive/qr-links.html', context)

def check_waiver_status(person_id):
    """ determine if a given person has a signed waiver """
    submitters = PersonDocuseal.objects.filter(person__id=person_id).values_list('submitter')
    waivers = DocusealSubmitterSubmission.objects.filter(
        submitter__in=submitters,
        submission__template__folder_name='Waivers',
        submission__status='completed'
        )
    return waivers.exists()

@csrf_exempt
def receive_webhook(request):
    """ Handle a Docuseal webhook """
    #!!! should webhooks be more selective?
    print(f"request.method: {request.method}")
    # need to valid webhook came from trusted source
    if request.method == 'POST':
        try:
            payload = json.loads(request.body.decode('utf-8'))

            Log.objects.create(description="Docuseal webhook", json=payload)

            # if payload['event_type'] == 'form.completed':
            #     print("form completed")
            #     email = payload['data']['email']
            #     print(f"email: {email}")
            #     name = payload['data']['name']
            #     print(f"name: {name}")
            #     submission_id = payload['data']['submission_id']
            #     print(f"submission_id: {submission_id}")
            #     phone = payload['data']['phone']
            #     print(f"phone: {phone}")
            #     completed_at = payload['data']['completed_at']
            #     print(f"completed_at: {completed_at}")
            #     status = payload['data']['status']
            #     print(f"status: {status}")
            #     role = payload['data']['role']
            #     print(f"role: {role}")
            #     values = payload['data']['values']
            #     print(f"values: {values}")
            # else:
            #     print("not a form completion webhook")

            webhook_refresh()
        
            return HttpResponse(status=200)
        
        except json.JSONDecodeError:
            return HttpResponse(status=400, reason="Invalid JSON payload")
    else:
        return HttpResponse(status=405, reason="Method not allowed")

@login_required
def docuseal_refresh_page(request):
    """ a page for initiating Docuseal data refreshes """
    # list the types of data refreshes
    # show last update from logs
    log_descriptions = [
        "Refresh DocusealTemplate",
        "Refresh DocusealSubmitter",
        "Refresh DocusealSubmission",
        "Refresh DocusealFieldStore",
    ]

    description = DOCUSEAL_API_ENDPOINT

    button_dict = [
            {'url_name': 'refresh_docuseal', 'anchor': 'Refresh Docuseal'},
    ]

    return refresh(request, log_descriptions, button_dict, description)

@login_required
def refresh_docuseal(request):
    """ force refresh Docuseal data """
    webhook_refresh()

    messages.success(request, f'Docuseal data refreshed')

    return redirect('docuseal_refresh')

def webhook_refresh():
    """ refresh data sets in order """
    DocusealTemplate.refresh()
    DocusealSubmitter.refresh()
    DocusealSubmission.refresh()
    DocusealFieldStore.refresh()