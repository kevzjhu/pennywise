from django.db import migrations

DEFAULT_CATEGORIES = [
    "Clothes", "Education", "Entertainment", "Groceries",
    "Health", "Home", "Miscellaneous", "Recurring Payment",
    "Rent", "Restaurants", "Transportation", "Travel"
]

def seed_categories(apps, schema_editor):
    Category = apps.get_model('transactions', 'Category')
    for cat_name in DEFAULT_CATEGORIES:
        Category.objects.get_or_create(name=cat_name)

class Migration(migrations.Migration):
    dependencies = [
        ('transactions', '0007_category_alter_transaction_category'),
    ]

    operations = [
        migrations.RunPython(seed_categories),
    ]