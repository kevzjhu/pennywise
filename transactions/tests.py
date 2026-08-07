from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import date
from transactions.models import (
    Category,
    Transaction,
    PaycheckTemplate,
    PaycheckTransaction,
    RecurringTransactionTemplate,
)
from dateutil.relativedelta import relativedelta

from transactions.forms import TransactionForm

from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
import csv
import io

# Create your tests here.

class CategoryModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        # Use get_or_create to account for the post_save signal
        self.category, _ = Category.objects.get_or_create(
            user=self.user, 
            name='TestGroceries', 
            defaults={'monthly_budget': Decimal('300.00')}
        )

    def test_category_creation(self):
        self.assertEqual(self.category.name, 'TestGroceries')
        self.assertEqual(self.category.monthly_budget, Decimal('300.00'))

    def test_category_unique_together(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Category.objects.create(user=self.user, name='TestGroceries')

    def test_category_str(self):
        self.assertEqual(str(self.category), 'TestGroceries')


class RecurringTransactionTemplateTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.category = Category.objects.create(user=self.user, name='Subscription', monthly_budget=50)
        self.template = RecurringTransactionTemplate.objects.create(
            user=self.user,
            description='Netflix',
            amount=15.99,
            category=self.category,
            frequency='MONTHLY',
            start_date=date(2026, 1, 1),
            end_date=None
        )

    def test_generate_historical_transactions(self):
        # Should create transactions for each month from start_date to today
        today = date.today()
        current = date(2026, 1, 1)
        expected_count = 0
        while current <= today:
            expected_count += 1
            current += relativedelta(months=1)

        created = self.template.generate_historical_transactions()
        self.assertEqual(created, expected_count)
        self.assertEqual(Transaction.objects.filter(user=self.user, recurring_template=self.template).count(), expected_count)

    def test_sync_missing_transactions(self):
        # Calculate expected count dynamically
        today = date.today()
        current = date(2026, 1, 1)
        expected = 0
        while current <= today:
            expected += 1
            current += relativedelta(months=1)

        self.template.generate_historical_transactions()
        tx = Transaction.objects.filter(user=self.user, recurring_template=self.template).first()
        tx.delete()
        
        self.template.sync_missing_transactions()
        self.assertEqual(Transaction.objects.filter(user=self.user, recurring_template=self.template).count(), expected)

class TransactionFormTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.category = Category.objects.create(user=self.user, name='Food', monthly_budget=200)

    def test_valid_form(self):
        form_data = {
            'date': '2026-08-06',
            'description': 'Lunch',
            'amount': 15.50,
            'category': self.category.id,
            'notes': 'Burger joint'
        }
        form = TransactionForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_invalid_form_missing_required(self):
        form = TransactionForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn('date', form.errors)
        self.assertIn('description', form.errors)
        self.assertIn('amount', form.errors)
        # category is optional, so not required

    def test_notes_max_length(self):
        long_notes = 'a' * 201
        form_data = {
            'date': '2026-08-06',
            'description': 'Test',
            'amount': 10,
            'category': self.category.id,
            'notes': long_notes
        }
        form = TransactionForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('notes', form.errors)

class HomeViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.login(username='testuser', password='testpass')

    def test_home_page_loads(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'transactions/home.html')

    def test_create_transaction(self):
        category = Category.objects.create(user=self.user, name='TestCat', monthly_budget=100)
        response = self.client.post(reverse('home'), {
            'date': '2026-08-06',
            'description': 'Test Transaction',
            'amount': 25.00,
            'category': category.id,
        })
        # Should redirect (or HTMX response)
        self.assertEqual(response.status_code, 302)  # Redirect to home
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)

    def test_csv_import_flow(self):
        # Create a CSV file in memory
        csv_content = "transaction_date,details,amount\n2026-08-01,Amazon purchase,45.99\n"
        csv_file = SimpleUploadedFile("test.csv", csv_content.encode('utf-8'), content_type="text/csv")

        # Stage the CSV (POST to home with action_type='stage_csv')
        response = self.client.post(reverse('home'), {
            'action_type': 'stage_csv',
            'bank': 'wealthsimple',
            'csv_file': csv_file,
        }, follow=True)

        # Should show the review modal with candidate rows
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Review Transactions to Import')
        # Check that the candidate row appears
        self.assertContains(response, 'Amazon purchase')

        # Now confirm import (select that row, assign category)
        category = Category.objects.create(user=self.user, name='Shopping', monthly_budget=200)
        post_data = {
            'action_type': 'confirm_csv_import',
            'selected_rows': ['0'],
            'date_0': '2026-08-01',
            'description_0': 'Amazon purchase',
            'amount_0': '45.99',
            'category_0': category.id,
        }
        response = self.client.post(reverse('home'), post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)

    def test_bulk_delete(self):
        # Create some transactions
        for i in range(3):
            Transaction.objects.create(user=self.user, date='2026-08-01', description=f'Tx{i}', amount=10)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 3)

        # Submit bulk delete with two IDs
        ids = list(Transaction.objects.filter(user=self.user).values_list('id', flat=True)[:2])
        response = self.client.post(reverse('home'), {
            'action_type': 'bulk_delete',
            'transaction_ids': ids,
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)


class AnalyticsViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.login(username='testuser', password='testpass')
        self.category = Category.objects.create(user=self.user, name='Food', monthly_budget=200)
        Transaction.objects.create(user=self.user, date='2026-08-01', description='Dinner', amount=30, category=self.category)
        Transaction.objects.create(user=self.user, date='2026-08-02', description='Lunch', amount=15, category=self.category)
        PaycheckTransaction.objects.create(user=self.user, date='2026-08-01', source_name='Employer', amount=1000)

    def test_analytics_page_loads(self):
        response = self.client.get(reverse('analytics'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'transactions/analytics.html')
        self.assertContains(response, 'Analytics Dashboard')

    def test_sankey_data_present(self):
        response = self.client.get(reverse('analytics'))
        self.assertEqual(response.status_code, 200)
        # Check that the sankey_data JSON is in context
        self.assertIn('sankey_data', response.context)
        # We can't easily assert the JSON content, but we can check it's not empty
        self.assertNotEqual(response.context['sankey_data'], '[]')

class BudgetsViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.login(username='testuser', password='testpass')

    def test_add_category(self):
        response = self.client.post(reverse('budgets'), {
            'action': 'add_category',
            'name': 'New Category',
            'monthly_budget': '150.00',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Category.objects.filter(user=self.user, name='New Category').exists())
        cat = Category.objects.get(user=self.user, name='New Category')
        self.assertEqual(cat.monthly_budget, Decimal('150.00'))

    def test_edit_category(self):
        cat = Category.objects.create(user=self.user, name='Old Name', monthly_budget=100)
        response = self.client.post(reverse('budgets'), {
            'action': 'edit_category',
            'category_id': cat.id,
            'name': 'New Name',
            'monthly_budget': '200.00',
        }, follow=True)
        cat.refresh_from_db()
        self.assertEqual(cat.name, 'New Name')
        self.assertEqual(cat.monthly_budget, Decimal('200.00'))

    def test_delete_category(self):
        cat = Category.objects.create(user=self.user, name='To Delete', monthly_budget=100)
        response = self.client.post(reverse('budgets'), {
            'action': 'delete_category',
            'category_id': cat.id,
        }, follow=True)
        self.assertFalse(Category.objects.filter(id=cat.id).exists())

class SettingsViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='oldpass')
        self.client.login(username='testuser', password='oldpass')

    def test_change_password(self):
        response = self.client.post(reverse('settings'), {
            'action': 'change_password',
            'old_password': 'oldpass',
            'new_password1': 'newpass123',
            'new_password2': 'newpass123',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newpass123'))

    def test_avatar_upload(self):
        # Create a small dummy image
        import io
        from PIL import Image
        img_io = io.BytesIO()
        img = Image.new('RGB', (100, 100), color='red')
        img.save(img_io, format='JPEG')
        img_io.seek(0)
        uploaded_file = SimpleUploadedFile('test.jpg', img_io.read(), content_type='image/jpeg')

        response = self.client.post(reverse('settings'), {
            'action': 'upload_avatar',
            'avatar': uploaded_file,
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.avatar)

class SettingsViewErrorHandlingTest(TestCase):
    """A failed or unknown settings POST must re-render, not 500."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='oldpass')
        self.client.login(username='testuser', password='oldpass')

    def test_failed_password_change_rerenders(self):
        response = self.client.post(reverse('settings'), {
            'action': 'change_password',
            'old_password': 'wrongpass',
            'new_password1': 'newpass123',
            'new_password2': 'mismatch456',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('profile_form', response.context)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('oldpass'))

    def test_unknown_action_rerenders(self):
        response = self.client.post(reverse('settings'), {'action': 'nonsense'})
        self.assertEqual(response.status_code, 200)


class FilterValidationTest(TestCase):
    """Malformed query params must be ignored, not raise."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.login(username='testuser', password='testpass')
        Transaction.objects.create(user=self.user, date='2026-08-01', description='Dinner', amount=30)
        PaycheckTransaction.objects.create(user=self.user, date='2026-08-01', source_name='Employer', amount=1000)

    def test_non_numeric_amount_bounds(self):
        for url in (reverse('home'), reverse('income')):
            response = self.client.get(url, {'min_amount': 'abc', 'max_amount': '!!'})
            self.assertEqual(response.status_code, 200)

    def test_malformed_dates_and_categories(self):
        response = self.client.get(reverse('home'), {
            'start_date': 'not-a-date',
            'end_date': '2026-13-45',
            'category': 'DROP TABLE',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dinner')


class AnalyticsEscapingTest(TestCase):
    """Category and income source names must not reach the page as raw script."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.login(username='testuser', password='testpass')
        cat = Category.objects.create(
            user=self.user, name='</script><script>alert(1)</script>', monthly_budget=100
        )
        Transaction.objects.create(
            user=self.user, date='2026-08-01', description='x', amount=10, category=cat
        )
        PaycheckTransaction.objects.create(
            user=self.user, date='2026-08-01', source_name='</script><img onerror=alert(2)>', amount=50
        )

    def test_no_script_breakout(self):
        response = self.client.get(reverse('analytics'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertNotIn('<script>alert(1)</script>', body)
        self.assertNotIn('<img onerror=alert(2)>', body)
        # json_script escapes the angle brackets instead
        self.assertIn('\\u003C', body)


class PaycheckTemplateEditTest(TestCase):
    """Editing a paycheck rule must not destroy manual overrides."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.login(username='testuser', password='testpass')
        self.template = PaycheckTemplate.objects.create(
            user=self.user,
            source_name='Employer',
            amount=Decimal('1000.00'),
            frequency='MONTHLY',
            start_date=date.today() - relativedelta(months=2),
        )
        self.template.generate_historical_paychecks()

    def test_edit_preserves_manual_override(self):
        overridden = PaycheckTransaction.objects.filter(template=self.template).first()
        overridden.amount = Decimal('1234.56')
        overridden.notes = 'bonus month'
        overridden.save()

        response = self.client.post(reverse('income'), {
            'form_type': 'recurring',
            'rule_id': self.template.id,
            'source_name': 'Employer',
            'amount': '1100.00',
            'frequency': 'MONTHLY',
            'start_date': self.template.start_date.strftime('%Y-%m-%d'),
        })
        self.assertEqual(response.status_code, 302)

        overridden.refresh_from_db()
        self.assertEqual(overridden.amount, Decimal('1234.56'))
        self.assertEqual(overridden.notes, 'bonus month')


class RecurringSyncOnGetTest(TestCase):
    """HTMX partial fetches must not write recurring rows."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.login(username='testuser', password='testpass')
        self.template = RecurringTransactionTemplate.objects.create(
            user=self.user,
            description='Netflix',
            amount=Decimal('15.99'),
            frequency='MONTHLY',
            start_date=date.today() - relativedelta(months=2),
        )

    def test_htmx_partial_does_not_sync(self):
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)
        response = self.client.get(reverse('home'), HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)

    def test_full_page_load_syncs(self):
        self.client.get(reverse('home'))
        self.assertGreater(Transaction.objects.filter(user=self.user).count(), 0)


class AdminImportScopingTest(TestCase):
    """Import rows must never resolve a related object owned by another user."""

    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='pass1')
        self.user2 = User.objects.create_user(username='user2', password='pass2')
        self.user1_category = Category.objects.create(
            user=self.user1, name='PrivateCat', monthly_budget=100
        )

    def test_category_not_borrowed_from_other_user(self):
        from transactions.admin import UserScopedForeignKeyWidget

        widget = UserScopedForeignKeyWidget(Category, field='name')
        with self.assertRaises(ValueError):
            widget.clean('PrivateCat', row={'user': 'user2'})

    def test_category_requires_user_column(self):
        from transactions.admin import UserScopedForeignKeyWidget

        widget = UserScopedForeignKeyWidget(Category, field='name')
        with self.assertRaises(ValueError):
            widget.clean('PrivateCat', row={})

    def test_category_resolves_for_owner(self):
        from transactions.admin import UserScopedForeignKeyWidget

        widget = UserScopedForeignKeyWidget(Category, field='name')
        self.assertEqual(widget.clean('PrivateCat', row={'user': 'user1'}), self.user1_category)


class DataIsolationTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='pass1')
        self.user2 = User.objects.create_user(username='user2', password='pass2')
        Transaction.objects.create(user=self.user1, date='2026-08-01', description='User 1 Expense', amount=50)

    def test_user_cannot_see_other_user_transactions(self):
        self.client.login(username='user2', password='pass2')
        response = self.client.get(reverse('home'))
        self.assertNotContains(response, 'User 1 Expense')