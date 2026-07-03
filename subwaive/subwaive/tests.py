from django.test import TestCase
from subwaive.models import Person
import time


class PersonTestCase(TestCase):
    def setUp(self):
        Person.objects.create(name="Test User")

    def test_person_has_created_at_field(self):
        """People should have a created_at field"""
        person = Person.objects.get(name="Test User")
        self.assertTrue(hasattr(person, "created_at"))

    def test_created_at_timestamps_are_unique(self):
        """created_at timestamps should be unique if users are not created at the same time"""
        person1 = Person.objects.create(name="Person One")
        time.sleep(0.1)
        person2 = Person.objects.create(name="Person Two")

        self.assertNotEqual(person1.created_at, person2.created_at)
        self.assertTrue(person1.created_at < person2.created_at)