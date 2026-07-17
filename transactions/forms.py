from django import forms
from .models import Transaction

class TransactionForm(forms.ModelForm):
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