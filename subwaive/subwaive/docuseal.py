import json
import os

from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt

from subwaive.models import DocusealFieldStore, DocusealSubmission, DocusealSubmitter, DocusealSubmitterSubmission, DocusealTemplate
from subwaive.models import Log
from subwaive.utils import generate_qr_svg, refresh, CONFIDENTIALITY_LEVEL_PUBLIC, QR_SMALL, QR_LARGE

DOCUSEAL_API_ENDPOINT = os.environ.get("DOCUSEAL_API_ENDPOINT")
DOCUSEAL_ENDPOINT_SECRET = os.environ.get("DOCUSEAL_ENDPOINT_SECRET")
DOCUSEAL_WWW_ENDPOINT = os.environ.get("DOCUSEAL_WWW_ENDPOINT")

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
    categories = sorted(categories, key=lambda x: x['name'])

    context = {
        'page_title': 'Links - Docuseal',
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_PUBLIC,
        'qr_list': template_list,
        'categories': categories,
    }

    return render(request, f'subwaive/qr-links.html', context)

@csrf_exempt
def receive_webhook(request):
    """ Handle a Docuseal webhook """

    print(f"request.method: {request.method}")
    # need to valid webhook came from trusted source
    if request.method == 'POST':
        signature = request.headers.get('X-Docuseal-Signature')
        if not signature:
            print(400, 'Missing signature')
            return HttpResponse(status=400, reason="Missing signature")

        # Docuseal does not implement HMAC signatures as of v1.9.0
        if signature == DOCUSEAL_ENDPOINT_SECRET:
            try:
                payload = json.loads(request.body.decode('utf-8'))

                Log.objects.create(description="Docuseal webhook", json=payload)

                print("webhook type: ",payload['event_type'] )

                # Probably not needed, but to prevent bad actors, we only accept information on 
                # which records to address from the webhook. We use the API to do the actual updates.
                if payload['event_type'] == 'form.completed':
                    # an individual has completed their portion of a form
                    # print(payload)
                    template_id = payload['data']['template']['id']
                    DocusealTemplate.create_or_update_by_id(template_id)

                    email = payload['data']['email']
                    DocusealSubmitter.create_if_needed(email)

                    submission_id = payload['data']['submission_id']
                    DocusealSubmission.create_or_update(submission_id)
                    DocusealFieldStore.re_extract(submission_id)

                elif payload['event_type'] == 'submission.created':
                    # a form has email addresses added for signatures
                    # print(payload)
                    template_id = payload['data']['template']['id']
                    DocusealTemplate.create_or_update_by_id(template_id)

                    for submitter in payload['data']['submitters']:
                        email = submitter['email']
                        DocusealSubmitter.create_if_needed(email)

                    submission_id = payload['data']['id']
                    DocusealSubmission.create_or_update(submission_id)
                    DocusealFieldStore.re_extract(submission_id)

                elif payload['event_type'] == 'form.declined':
                    # an individual has declined to sign a form?
                    #!!! we might want to know about declined or started forms at some point
                    pass

                elif payload['event_type'] in ['template.created','template.updated']:
                    # a new form is created or an existing one is altered
                    template_id = payload['data']['id']
                    DocusealTemplate.create_or_update_by_id(template_id)

                elif payload['event_type'] == 'submission.archived':
                    # a submitted form is archived
                    submission_id = payload['data']['id']
                    template_id = payload['data']['template']['id']
                    DocusealTemplate.create_or_update_by_id(template_id)
                    DocusealSubmission.create_or_update(submission_id)
                    DocusealFieldStore.re_extract(submission_id)

                else:
                    # some other kind of webhook was received
                    print("unhandled webhook event_type")
            
                return HttpResponse(status=200)
            
            except json.JSONDecodeError:
                return HttpResponse(status=400, reason="Invalid JSON payload")
        else:
            print(401, 'Invalid signature')
            return HttpResponse(status=401, reason="Invalid signature")

    else:
        return HttpResponse(status=405, reason="Method not allowed")

@login_required
def docuseal_refresh_page(request):
    """ a page for initiating Docuseal data refreshes """
    page_title = 'Refresh Docuseal Data'
    data_source = DOCUSEAL_API_ENDPOINT

    button_dict = [
        {'url': DOCUSEAL_WWW_ENDPOINT, 'anchor': 'Docuseal', 'class': 'info', 'active': True},
    ]

    tiles = [
        {
            'buttons': [
                {'url_name': 'refresh_docuseal', 'anchor': 'Refresh All Docuseal'},
                {'url_name': 'fetch_new_docuseal', 'anchor': 'Fetch New Docuseal'},
            ],
            'log_descriptions': [
                {'description': 'DocusealTemplate'},
                {'description': 'DocusealSubmitter'},
                {'description': 'DocusealSubmission'},
                {'description': 'DocusealFieldStore'},
            ]
        },

    ]

    return refresh(request, page_title, data_source, tiles, button_dict)

@login_required
def fetch_new_docuseal(request):
    """ force pull of new Docuseal docs """
    print("fetch_new_docuseal")
    return refresh_docuseal(request, new_only=True)

@login_required
def refresh_docuseal(request, new_only=False):
    """ force refresh Docuseal data """
    refresh_all(new_only)

    messages.success(request, f'Docuseal data refreshed')

    return redirect('docuseal_refresh')

def refresh_all(new_only=False):
    """ refresh data sets in order """
    DocusealTemplate.refresh(new_only)
    DocusealSubmitter.refresh(new_only)
    max_existing_submission_id = None
    if new_only:
        max_existing_submission_id = DocusealSubmission.objects.all().order_by('-submission_id').first().submission_id
    DocusealSubmission.refresh(new_only)
    DocusealFieldStore.refresh(max_existing_submission_id)