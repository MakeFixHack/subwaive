import datetime
import json
import os

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt

import stripe

from subwaive.models import StripePaymentLink,StripePrice,StripeProduct,StripePaymentLinkPrice,StripeSubscription,StripeCustomer
from subwaive.utils import generate_qr_svg, refresh, CONFIDENTIALITY_LEVEL_PUBLIC, QR_SMALL, QR_LARGE

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY")
STRIPE_ENDPOINT_SECRET = os.environ.get("STRIPE_ENDPOINT_SECRET")
STRIPE_WWW_ENDPOINT = os.environ.get("STRIPE_WWW_ENDPOINT")

DATA_REFRESH_TOKEN = os.environ.get("DATA_REFRESH_TOKEN")

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
    categories = sorted(categories, key=lambda x: x['name'])

    context = {
        'page_title': 'Links - Stripe',
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_PUBLIC,
        'categories': categories,
        'qr_list': stripe_qr_list,
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
        refresh_all_subscription_and_customer()

    elif event.type in ['invoice.paid','invoice.payment_failed']:
        refresh_all_subscription_and_customer()

    elif event.type in ['payment_link.created','payment_link.updated']:
        # payment_link = StripePaymentLink.objects.get(payload['id'])
        # payment_link.whatever = some_val
        # payment_link.save()
        refresh_all_product_and_price()

    else:
        # need to handle everything we use
        print('Unhandled event type {}'.format(event.type))

    return HttpResponse(status=200)

@csrf_exempt
def refresh_stripe_by_token(request):
    """ allow Stripe data refresh by token """

    if request.headers.get('X-Refresh-Token') == DATA_REFRESH_TOKEN:
        print(datetime.datetime.now(), "Refreshing Stripe products and prices by token")
        refresh_all_product_and_price()
        print(datetime.datetime.now(), "Refreshing Stripe subscriptions and customers by token")
        refresh_all_subscription_and_customer()

        return HttpResponse(status=200)
    else:
        return HttpResponse(status=401)

@login_required
def refresh_product_and_price(request):
    """ force refresh Stripe payment links and associated data """
    refresh_all_product_and_price()

    messages.success(request, f'Stripe Product and Price data refreshed')

    return redirect('stripe_refresh')

@login_required
def fetch_product_and_price(request):
    """ force refresh Stripe payment links and associated data """
    fetch_new_product_and_price()

    messages.success(request, f'Fetched new Stripe Product and Price data')

    return redirect('stripe_refresh')

def fetch_new_product_and_price():
    refresh_all_product_and_price(True)
    
def refresh_all_product_and_price(new_only=False):
    StripeProduct.refresh(new_only)
    StripePaymentLink.refresh(new_only)
    StripePrice.refresh(new_only)
    StripePaymentLinkPrice.refresh()

@login_required
def refresh_subscription_and_customer(request):
    """ force refresh Stripe subscriptions and customers """
    refresh_all_subscription_and_customer()

    messages.success(request, f'Stripe Subscription and Customer data refreshed')

    return redirect('stripe_refresh')

@login_required
def fetch_subscription_and_customer(request):
    """ force refresh Stripe subscriptions and customers """
    fetch_new_subscription_and_customer()

    messages.success(request, f'Fetched new Stripe Subscription and Customer data')

    return redirect('stripe_refresh')

def fetch_new_subscription_and_customer():
    refresh_all_subscription_and_customer(True)

def refresh_all_subscription_and_customer(new_only=False):
    StripeCustomer.refresh(new_only)
    StripeSubscription.refresh(new_only)

@login_required
def stripe_refresh_page(request):
    """ a page for initiating Stripe data refreshes """
    page_title = 'Stripe Data'
    data_source = STRIPE_WWW_ENDPOINT

    button_dict = [
        {'url': STRIPE_WWW_ENDPOINT, 'anchor': 'Stripe Dashboard', 'class': 'info', 'active': True},
    ]

    tiles = [
        {
            'title': 'Products, Prices, & Links',
            'buttons': [
                {'url_name': 'refresh_product_and_price', 'anchor': 'Refresh All Products and Prices'},
                {'url_name': 'fetch_product_and_price', 'anchor': 'Fetch New Products and Prices'},
            ],
            'log_descriptions': [
                {'description': 'StripeProduct'},
                {'description': 'StripePrice'},
                {'description': 'StripePaymentLink'},
            ]
        },
        {
            'title': 'Customers & Subscriptions',
            'buttons': [
                {'url_name': 'refresh_subscription_and_customer', 'anchor': 'Refresh All Subscriptions and Customers'},
                {'url_name': 'fetch_subscription_and_customer', 'anchor': 'Fetch New Subscriptions and Customers'},
            ],
            'log_descriptions': [
                {'description': 'StripeCustomer'},
                {'description': 'StripeSubscription'},
            ]
        },
    ]

    return refresh(request, page_title, data_source, tiles, button_dict)