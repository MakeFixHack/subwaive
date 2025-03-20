import json
import os

from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse

import stripe

from subwaive.models import Person
from subwaive.models import StripePaymentLink,StripePrice,StripeProduct,StripePaymentLinkPrice,StripeSubscription,StripeCustomer
from subwaive.utils import generate_qr_svg, refresh, CONFIDENTIALITY_LEVEL_PUBLIC, CONFIDENTIALITY_LEVEL_HIGH, QR_SMALL, QR_LARGE

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY")
STRIPE_ENDPOINT_SECRET = os.environ.get("STRIPE_ENDPOINT_SECRET")

def check_membership_status(person_id):
    """ return true if they have a current membership """
    has_membership = False
    if Person.objects.filter(id=person_id).first().get_memberships():
        has_membership = True

    return has_membership 

@login_required
def payment_link_list(request):
    """ Show QR codes and details for Stripe PaymentLinks """
    stripe_qr_codes = StripePaymentLinkPrice.objects.all().order_by('price__product__name','price__interval','price__price')

    stripe_qr_list = [
        {
            'id' : qr.id,
            'category': qr.price.product.name,
            'name': f"{ qr.price }",
            'svg_small': generate_qr_svg(qr.payment_link.url, QR_SMALL),
            'svg_large': generate_qr_svg(qr.payment_link.url, QR_LARGE),
        }
        for qr in stripe_qr_codes
    ]

    categories = [
        {
            'name': product,
            'baseid': f'cat-{ indx }',
        }
        for indx,product in enumerate(set([sqc.price.product.name for sqc in stripe_qr_codes]))
    ]

    button_dict = [
            {'url': reverse('custom_link_list'), 'anchor': 'Custom'},
            {'url': reverse('payment_link_list'), 'anchor': 'Stripe', 'active': True},
            {'url': reverse('docuseal_link_list'), 'anchor': 'Docuseal'},
    ]

    context = {
        'page_title': 'Links - Stripe',
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_PUBLIC,
        'categories': categories,
        'qr_list': stripe_qr_list,
        'buttons': button_dict,
    }

    return render(request, f'subwaive/qr-links.html', context)

@csrf_exempt
def receive_webhook(request):
    """ handle Stripe webhooks """
    """
    customer.subscription.deleted - log
    invoice.paid - log
    invoice.payment_failed - log
    payment_link.created - trigger update of payment links
    payment_link.updated - trigger update of payment links
    """
    #!!! should webhooks be more focused?
    # https://docs.stripe.com/webhooks
    payload = request.body
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']
    event = None

    try:
        event = stripe.Event.construct_from(
            json.loads(payload), sig_header, STRIPE_ENDPOINT_SECRET
        )
    except ValueError as e:
    # Invalid payload
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        print('Error verifying webhook signature: {}'.format(str(e)))
        return HttpResponse(status=400)
    
    # Handle the event
    #!!! parse webhooks and get the specific entity that needs creating or updating
    #!!! limit updates to what needs updating
    payload = event.data.object
    if event.type == 'customer.subscription.deleted':
        # StripeSubscription.objects.get(payload['id']).delete()
        webhook_subscription_and_customer()

    elif event.type in ['invoice.paid','invoice.payment_failed']:
        webhook_subscription_and_customer()

    elif event.type in ['payment_link.created','payment_link.updated']:
        # payment_link = StripePaymentLink.objects.get(payload['id'])
        # payment_link.whatever = some_val
        # payment_link.save()
        webhook_refresh_product_and_price()

    else:
        # need to handle everything we use
        print('Unhandled event type {}'.format(event.type))

    return HttpResponse(status=200)

@login_required
def refresh_product_and_price(request):
    """ force refresh Stripe payment links and associated data """
    webhook_refresh_product_and_price()

    return redirect('stripe_refresh')

def webhook_refresh_product_and_price():
    StripeProduct.refresh()
    StripePaymentLink.refresh()
    StripePrice.refresh()
    StripePaymentLinkPrice.refresh()

@login_required
def refresh_subscription_and_customer(request):
    """ force refresh Stripe subscriptions and customers """
    webhook_subscription_and_customer()

    return redirect('stripe_refresh')

def webhook_subscription_and_customer():
    StripeCustomer.refresh()
    StripeSubscription.refresh()

@login_required
def stripe_refresh_page(request):
    """ a page for initiating Stripe data refreshes """
    # list the types of data refreshes
    # show last update from logs
    log_descriptions = [
        "Refresh StripeProduct",
        "Refresh StripePrice",
        "Refresh StripePaymentLink",
        "Refresh StripeCustomer",
        "Refresh StripeSubscription"
    ]

    button_dict = [
            {'url_name': 'refresh_product_and_price', 'anchor': 'Refresh Products and Prices'},
            {'url_name': 'refresh_subscription_and_customer', 'anchor': 'Refresh Subscriptions and Customers'},
    ]

    return refresh(request, log_descriptions, button_dict)