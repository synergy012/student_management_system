"""
Simple Working AcroForms Example - Minimal implementation to prove it works
"""

from reportlab.platypus import SimpleDocTemplate, Flowable, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter

class TextField(Flowable):
    def __init__(self, name, value="", width=150, height=20, **kwargs):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.name = name
        self.value = value
        self.kwargs = kwargs

    def draw(self):
        form = self.canv.acroForm
        form.textfieldRelative(
            name=self.name,
            value=self.value,
            width=self.width,
            height=self.height,
            forceBorder=True,
            **self.kwargs
        )

class CheckboxField(Flowable):
    def __init__(self, name, checked=False, size=12, **kwargs):
        Flowable.__init__(self)
        self.width = size
        self.height = size
        self.name = name
        self.checked = checked
        self.kwargs = kwargs

    def draw(self):
        form = self.canv.acroForm
        form.checkboxRelative(
            name=self.name,
            checked=self.checked,
            size=self.width,
            forceBorder=True,
            **self.kwargs
        )

class ChoiceField(Flowable):
    def __init__(self, name, options, value=None, width=150, height=20, **kwargs):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.name = name
        self.options = options
        self.value = value or (options[0] if options else "")
        self.kwargs = kwargs

    def draw(self):
        form = self.canv.acroForm
        # Use textfield with combo flag for dropdown
        form.textfieldRelative(
            name=self.name,
            value=self.value,
            width=self.width,
            height=self.height,
            forceBorder=True,
            fieldFlags='combo',
            **self.kwargs
        )

def create_simple_fillable_pdf():
    """Create a simple working fillable PDF"""
    doc = SimpleDocTemplate('simple_fillable.pdf', pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    story.append(Paragraph("Simple Fillable PDF Test", styles['Title']))
    story.append(Spacer(1, 20))
    
    # Text fields
    story.append(Paragraph("Student Name:", styles['Normal']))
    story.append(TextField(name='student_name', width=250, height=24))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("Email:", styles['Normal']))
    story.append(TextField(name='email', width=250, height=24))
    story.append(Spacer(1, 10))
    
    # Checkbox
    story.append(Paragraph("Check if you agree:", styles['Normal']))
    story.append(CheckboxField(name='agree', size=15))
    story.append(Spacer(1, 10))
    
    # Simple dropdown (using textfield with combo flag)
    story.append(Paragraph("Division:", styles['Normal']))
    story.append(ChoiceField(
        name='division',
        options=['YZA', 'YOH', 'KOLLEL'],
        value='YZA',
        width=120,
        height=24
    ))
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("This PDF should have working fillable fields!", styles['Normal']))
    
    doc.build(story)
    print("✅ Simple fillable PDF created: simple_fillable.pdf")
    return "simple_fillable.pdf"

if __name__ == "__main__":
    try:
        create_simple_fillable_pdf()
        print("SUCCESS: AcroForms work with the free version of ReportLab!")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc() 