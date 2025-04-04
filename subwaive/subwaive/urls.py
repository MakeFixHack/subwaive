from django.contrib import admin
from django.urls import path

from subwaive import docuseal
from subwaive import views
from subwaive import stripe

# Admin
urlpatterns = [
    path('admin/', admin.site.urls),
]

# SubWaive
urlpatterns = [
    path('', views.public_link_list),
    path('email/<int:email_id>/unmerge/', views.unmerge_people, name='unmerge_people'),
    path('email/<int:email_id>/prefer/', views.set_preferred_email, name='set_preferred_email'),
    path('event/<int:event_id>/', views.event_details, name='event_details'),
    path('event/list/', views.event_list, name='event_list'),
    path('event/list/<timeframe>/', views.event_list, name='event_list'),
    path('event/refresh/', views.event_refresh_page, name='event_refresh'),
    path('event/refresh/all/', views.refresh_event, name='refresh_event'),
    path('links/public/', views.public_link_list, name='public_link_list'),
    path('links/internal/', views.sensitive_link_list, name='sensitive_link_list'),
    path('person/search/', views.person_search, name='person_search'),
    path('person/list/', views.person_list, name='person_list'),
    path('person/<int:person_id>/check-in/<int:event_id>/delete/', views.delete_member_check_in, name='delete_member_check_in'),
    path('person/<int:person_id>/', views.person_card, name='person_card'),
    path('person/<int:person_id>/event/<int:event_id>/check-in/', views.member_check_in, name='member_check_in'),
    path('person/<int:person_id>/event/<int:event_id>/check-in/force/', views.force_member_check_in, name='force_member_check_in'),
    path('person/<int:person_id>/check-in/remediate/', views.check_in_remediation, name='check_in_remediation'),
    path('person/<int:person_id>/docuseal/', views.person_docuseal, name='person_docuseal'),
    path('person/<int:person_id>/edit/', views.person_edit, name='person_edit'),
    path('person/<int:person_id>/name/<int:important_field_id>/docuseal/', views.set_docuseal_name, name='set_docuseal_name'),
    path('person/<int:person_id>/name/<stripe_id>/stripe/', views.set_stripe_name, name='set_stripe_name'),
    path('person/<int:merge_child_id>/merge/', views.merge_people, name='merge_people'),
    path('person/<int:merge_child_id>/merge/<int:merge_parent_id>/', views.merge_people, name='merge_people'),
    path('person/<int:person_id>/stripe/', views.person_stripe, name='person_stripe'),
]

# Docuseal
urlpatterns.extend([
    path('docuseal/links/', docuseal.qr_links, name='docuseal_link_list'),
    path('docuseal/refresh/', docuseal.docuseal_refresh_page, name='docuseal_refresh'),
    path('docuseal/refresh/all/', docuseal.refresh_docuseal, name='refresh_docuseal'),
    path('docuseal/refresh/new/', docuseal.fetch_new_docuseal, name='fetch_new_docuseal'),
    path('docuseal/webhook/', docuseal.receive_webhook, name='receive_webhook'),
])

# Stripe
urlpatterns.extend([
    path('stripe/links/', stripe.payment_link_list, name='payment_link_list'),
    path('stripe/refresh/', stripe.stripe_refresh_page, name='stripe_refresh'),
    path('stripe/fetch-new/payment-links/', stripe.fetch_new_product_and_price, name='fetch_new_product_and_price'),
    path('stripe/fetch-new/subscriptions/', stripe.fetch_new_subscription_and_customer, name='fetch_new_subscription_and_customer'),
    path('stripe/refresh/payment-links/', stripe.refresh_product_and_price, name='refresh_product_and_price'),
    path('stripe/refresh/subscriptions/', stripe.refresh_subscription_and_customer, name='refresh_subscription_and_customer'),
    path('stripe/webhook/', stripe.receive_webhook, name='receive_webhook'),
])
