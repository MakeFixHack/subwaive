import datetime
import os

from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt

from subwaive.models import DocusealTemplate
from subwaive.models import Event
from subwaive.models import NFC
from subwaive.models import Person, PersonEmail, PersonEvent
from subwaive.utils import generate_qr_bitmap, send_email, url_secret

SELF_SERVE_TOKEN = os.environ.get("SELF_SERVE_TOKEN")
TIME_ZONE = os.environ.get("TIME_ZONE")

@csrf_exempt
def nfc_self_serve(request):
    """ self-serve terminal interface for NFC check-in and self-serve sign-up """
    # !!! depends on Event.get_registration_url()

    response = HttpResponse(status=401)

    # print(f"token: {request.headers.get('X-Self-Serve-Token')}")
    # print(f"http-payload: {request.POST}")

    if request.headers.get('X-Self-Serve-Token') == SELF_SERVE_TOKEN:
        uid = request.POST.get("uid", None)
        # print(f"uid: {uid}")
        nfc_qs = NFC.objects.filter(uid=uid)

        if not nfc_qs.exists():
            print("nfc not in database")
            # store NFC
            nfc = NFC.objects.create(uid=uid, nfc_id=url_secret(), activation_id=url_secret())
            # create link to register NFC
            url = request.build_absolute_uri(redirect('register_nfc', nfc.nfc_id).url)
            (bmp,qr_size) = generate_qr_bitmap(url)
            # print(bmp)
            response = HttpResponse(
                content=bmp, 
                content_type="text/bitmap",
                status=200,
                headers={'line1': 'Register', 'line2': 'NFC', 'qr_size': qr_size})
            
        else:
            print("nfc found in database")
            last_check_in = None

            person = nfc_qs.first().person
            if person:
                last_check_in = person.get_last_check_in()
                event = Event.get_current_event()
                is_event_requires_registration = False
                if event:
                    if event.get_registration_link():
                        is_event_requires_registration = True


            is_last_check_in_date_today = False
            if last_check_in:
                print("found prior check-in")
                print(last_check_in.check_in_time)
                print(last_check_in.check_in_time.date())
                print(datetime.date.today())
                if last_check_in.event:
                    if last_check_in.event.start.date() == datetime.date.today():
                        print("last event check in was today")
                        is_last_check_in_date_today = True
                elif last_check_in.check_in_time.date() == datetime.date.today():
                    print("last ad hoc check in was today")
                    is_last_check_in_date_today = True
            print(f"is_last_check_in_date_today: {is_last_check_in_date_today}")

            if person and not nfc_qs.first().is_active:
                print("uid is attached to person but not activated")
                response = HttpResponse(
                    status=200,
                    headers={'line1': 'Check', 'line2': 'Email', 'line3': 'Activate', 'line4': 'NFC'})

            elif not person:
                print("uid not connected with a person")
                NFC.objects.filter(uid=uid).delete()
                nfc = NFC.objects.create(uid=uid, nfc_id=url_secret(), activation_id=url_secret())
                url = request.build_absolute_uri(redirect('register_nfc', nfc.nfc_id).url)
                (bmp,qr_size) = generate_qr_bitmap(url)
                response = HttpResponse(
                    content=bmp, 
                    content_type="text/bitmap",
                    status=200,
                    headers={'line1': 'Register', 'line2': 'NFC', 'qr_size': qr_size})

            elif not person.check_waiver_status():
                print("needs waiver")
                url = DocusealTemplate.objects.filter(folder_name='Waivers').first().get_url()
                (bmp,qr_size) = generate_qr_bitmap(url)
                response = HttpResponse(
                    content=bmp, 
                    content_type="text/bitmap",
                    status=200,
                    headers={'line1': 'Sign', 'line2': 'Waiver', 'qr_size': qr_size})

            elif not person.check_membership_status() and not person.get_events():
                print("needs membership")
                url = "https://www.makefixhack.org/p/membership-and-donation.html"
                (bmp,qr_size) = generate_qr_bitmap(url)
                response = HttpResponse(
                    content=bmp, 
                    content_type="text/bitmap",
                    status=200,
                    headers={'line1': 'Membership', 'line2': 'Needed', 'qr_size': qr_size})

            elif is_last_check_in_date_today:
                print("already checked-in")
                response = HttpResponse(
                    status=200,
                    headers={'bgColor': 'green', 'line1': 'Welcome', 'line2': 'Back!'})
            
            else:
                print("check-in succeeded")
                check_in = person.check_in()
                check_in.save()
                print(check_in)
                response = HttpResponse(
                    status=200,
                    headers={'bgColor': 'green', 'line1': 'Welcome', 'line2': 'Back!'})

    else:
        print("unauthorized")
        response = HttpResponse(status=401)

    # print(response.headers)
    return response
    
def register_nfc(request, nfc_id):
    """ register an NFC UID to a person """
    context = {}
    email = request.POST.get("email", None)
    nfc_qs = NFC.objects.filter(nfc_id=nfc_id)

    # https://docs.djangoproject.com/en/5.2/topics/email/

    if nfc_qs.exists():
    # if random id in db and is_confirmed=False, confirm and print msg "done"
        nfc = nfc_qs.first()
        email = request.POST.get("email", None)

        if nfc.person:
            context['action'] = 'reject'
            context['message'] = "This NFC token has already been associated with a person. Check your email for a confirmation link."
        elif email:
            person_qs = PersonEmail.objects.filter(email=email)
            if person_qs.exists():
                context['action'] = 'direct_activate'
                nfc.person = person_qs.first().person
                nfc.confirmation_id = url_secret()
                nfc.save()
                
                url = request.build_absolute_uri(redirect('activate_nfc', nfc.activation_id).url)
                email_body=f"""Activate your NFC token
                An NFC card/sticker was registered with MakeFixHack for this email address. This will allow you to check-in using our self check-in system.
                {url}
                
                Didn't request this? You can ignore it and it will expire."""
                email_html_body=f"""<h1>Activate your NFC token</h1>
                <p>An NFC card/sticker was registered with MakeFixHack for this email address. This will allow you to check-in using our self check-in system.</p>
                <p><a href="{url}"><button onclick="false;">Activate</button></a></p>
                <hr>
                <p>Didn't request this? You can ignore it and it will expire.</p>"""
                send_email(email_to_address=email, email_body=email_body, email_html_body=email_html_body, email_subject="Activate your NFC token")
                context['message'] = "This NFC token has been associated with your email address. Check that email for a confirmation link."
            else:
                context['action'] = 'direct_sign_up'
                context['message'] = "The email address provided wasn't found in the database. Sign-up and try again."
                context['link'] = redirect('self_check_in_email').url
        elif nfc:
            # elif no-email-provided, prompt for email address
            context['action'] = 'collect_email'
        else:
            context['action'] = 'nfc_not_found'

    else:
        context['message'] = "This NFC link is not in the database."
    
    return render(request, f'subwaive/nfc/nfc-register.html', context)

def activate_nfc(request, activation_id):
    """ demonstrate ownership of email address associated with NFC UID """
    context = {}
    nfc_qs = NFC.objects.filter(activation_id=activation_id)

    if nfc_qs.exists():
    # if id in db and is_confirmed=False, confirm and print msg "done"
        nfc = nfc_qs.first()

        if nfc.is_active:
            context['action'] = 'already_active'
        
        else: # !!! add elif for expired request
            nfc.is_active = True
            nfc.save()
            context['action'] = "activation_success"

    else:
        context['action'] = "nfc_not_found"

    return render(request, f'subwaive/nfc/nfc-activate.html', context)
