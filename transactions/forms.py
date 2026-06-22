from django import forms


class StatementUploadForm(forms.Form):
    statement = forms.FileField(
        label='Credit card statement PDF',
        help_text='Upload a PDF file containing your credit card statement.',
        widget=forms.FileInput(attrs={'accept': '.pdf'}),
    )
