"""Known-defect injection proves the manuscript structural checks reject defects."""
import importlib.util
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('checker',HERE/'check_template_conformance.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)

class ConformanceTest(unittest.TestCase):
    def setUp(self):
        self.source=(checker.ROOT/'paper/manuscript.md').read_text(encoding='utf-8')
        self.doc=HERE/'output/manuscript.docx'
    def test_valid_draft(self): self.assertEqual(checker.audit(self.source,self.doc),[])
    def test_wrong_abstract_length(self):
        self.assertTrue(checker.audit(self.source.replace('Purpose: To assess','Purpose: To independently assess'),self.doc))
    def test_missing_declaration(self):
        self.assertTrue(checker.audit(self.source.replace('### Funding statement','### Other statement'),self.doc))
    def test_figure_order(self):
        self.assertTrue(checker.audit(self.source.replace('Figure 1 presents','Figure 3 presents'),self.doc))
    def test_missing_reference(self):
        self.assertTrue(checker.audit(self.source.replace('[2]',''),self.doc))
    def test_markup_printed_as_text(self):
        """Four Crossref container titles once printed as 'Physics in Medicine &amp; Biology'.

        Doubling the escape in the document XML reproduces the defect exactly: the
        reader of the .docx then sees the entity rather than the ampersand.
        """
        with tempfile.TemporaryDirectory() as tmp:
            injected=Path(tmp)/'manuscript.docx'
            with zipfile.ZipFile(self.doc) as src, zipfile.ZipFile(injected,'w') as dst:
                for item in src.infolist():
                    data=src.read(item.filename)
                    if item.filename=='word/document.xml':
                        data=data.replace(b'Physics in Medicine',b'Physics in Medicine &amp;amp;',1)
                    dst.writestr(item,data)
            found=checker.audit(self.source,injected)
            self.assertTrue(found,'the markup rule did not fire on a planted entity')
            self.assertTrue(any('Markup printed as text' in f for f in found),found)

class CleanedReferenceTest(unittest.TestCase):
    """The defect the rule above describes was real: prove it on the live metadata."""
    def test_crossref_metadata_still_carries_markup(self):
        spec=importlib.util.spec_from_file_location('builder',HERE/'build_submission_docs.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        raw,builder.clean=builder.clean,lambda s:str(s)
        try: unclean=builder.refs_text()
        finally: builder.clean=raw
        self.assertIn('&amp;',unclean)          # without clean(), the entity is printed
        self.assertNotIn('&amp;',builder.refs_text())
    def test_title_override_is_applied(self):
        text=self.rendered()
        self.assertIn('Low-dose CT via convolutional neural network',text)
        self.assertNotIn('aLow-dose',text)
    def rendered(self):
        spec=importlib.util.spec_from_file_location('builder',HERE/'build_submission_docs.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        return builder.refs_text()
    def test_initials_registered_without_spaces_are_kept(self):
        """'F.R.' is one token; splitting on spaces alone rendered it as 'F'."""
        self.assertIn('Verdun FR',self.rendered())
    def test_author_override_is_applied(self):
        """One Crossref record holds the whole name in the family field."""
        text=self.rendered()
        self.assertIn('Wang Z, Bovik AC, Sheikh HR, Simoncelli EP',text)
        self.assertNotIn('Zhou Wang',text)
    def test_multiword_surnames_survive(self):
        text=self.rendered()
        for name in ('De Man B','La Rivière PJ','Sanchez del Rio M'):
            self.assertIn(name,text)

if __name__=='__main__':unittest.main()
