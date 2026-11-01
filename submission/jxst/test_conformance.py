"""Known-defect injection proves the manuscript structural checks reject defects."""
import importlib.util
import unittest
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

if __name__=='__main__':unittest.main()
