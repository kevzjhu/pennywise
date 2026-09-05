from django import forms
from .models import Transaction, Category, PaycheckTransaction, PaycheckTemplate, RecurringTransactionTemplate, Profile

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['avatar']

class RecurringTransactionTemplateForm(forms.ModelForm):
    class Meta:
        model = RecurringTransactionTemplate
        fields = ['description', 'amount', 'category', 'frequency', 'start_date', 'end_date', "notes"]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'placeholder': 'Enter default notes for recurring entries...', 'rows': 3, 'maxlength': 200}),
        }

    def clean_notes(self):
        notes = self.cleaned_data.get('notes')
        if notes and len(notes) > 200:
            raise forms.ValidationError("Notes cannot exceed 200 characters.")
        return notes

class TransactionForm(forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),  # 🔤 Pulls dynamically from Category table
        required=False,
        empty_label="Select Category",
        widget=forms.Select(attrs={
            'class': 'w-full text-sm border border-gray-300 rounded-lg p-2 focus:ring-blue-500 focus:border-blue-500'
        })
    )

    class Meta:
        model = Transaction
        fields = ['date', 'description', 'amount', 'category', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.TextInput(attrs={'placeholder': 'Enter transaction description'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'placeholder':  'Enter transaction amount'}),
            'category': forms.Select(attrs={'placeholder': 'Select transaction category'}),
            'notes': forms.Textarea(attrs={'placeholder': 'Enter transaction notes', 'rows': 4, 'maxlength': 200}),
        }

    # Hard backend validation
    def clean_notes(self):
        notes = self.cleaned_data.get('notes')
        if notes and len(notes) > 200:
            raise forms.ValidationError("Notes cannot exceed 200 characters.")
        return notes

class BulkCategoryForm(forms.Form):
    category = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        required=True,
        empty_label="Assign category...",
        widget=forms.Select(attrs={
            'class': 'text-xs border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg px-2 py-1.5 focus:ring-blue-500 focus:border-blue-500'
        })
    )

class PaycheckTemplateForm(forms.ModelForm):
    class Meta:
        model = PaycheckTemplate
        fields = ['source_name', 'amount', 'frequency', 'start_date', 'end_date', 'notes']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'placeholder': 'Enter default notes for recurring paychecks...', 'rows': 3, 'maxlength': 200}),
        }

    def clean_notes(self):
        notes = self.cleaned_data.get('notes')
        if notes and len(notes) > 200:
            raise forms.ValidationError("Notes cannot exceed 200 characters.")
        return notes

class PaycheckTransactionForm(forms.ModelForm):
    class Meta:
        model = PaycheckTransaction
        fields = ['date', 'source_name', 'amount', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'placeholder': 'Enter paycheck notes...', 'rows': 3, 'maxlength': 200}),
        }

    def clean_notes(self):
        notes = self.cleaned_data.get('notes')
        if notes and len(notes) > 200:
            raise forms.ValidationError("Notes cannot exceed 200 characters.")
        return notes
