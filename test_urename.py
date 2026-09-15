import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest

import uRename as app


class MaskTests(unittest.TestCase):
    def test_instruction_forms(self):
        forms = ["инструкция", "инструкции", "инструкцию", "инструкцией",
                 "инструкциею", "инструкций", "инструкциям", "инструкциями", "инструкциях"]
        for form in forms:
            for separator in ["_", " ", ". ", "-"]:
                with self.subTest(form=form, separator=separator):
                    source = f"3_41{separator}{form.upper()}{separator}Ветацеф"
                    self.assertEqual(app.apply_mask(source, "99_999_Aaaaaaaaaa", True),
                                     "03_041_Vetatsef")

    def test_instruction_mode_off_and_word_boundaries(self):
        self.assertEqual(app.apply_mask("15_Инструкция Ветацеф", "999_Aaaaaaaaaa"),
                         "015_Instruktsi")
        for word in ["видеоинструкция", "инструкционный", "инструкция2", "xинструкция"]:
            with self.subTest(word=word):
                self.assertEqual(app.INSTRUCTION_RE.sub(" ", word), word)
        self.assertEqual(app.apply_mask("15_Инструкция_инструкции_Ветацеф",
                                        "99_999_Aaaaaaaaaa", True), "015_Vetatsef")

    def test_requested_examples(self):
        for source, expected in [
            ("11_15_тексттексттекст", "11_015_TEKSTTE"),
            ("15_тексттексттекст", "015_TEKSTTE"),
            ("1_2_тексттекст", "01_002_TEKSTTE"),
            ("тексттекст", "TEKSTTE"),
        ]:
            with self.subTest(source=source):
                self.assertEqual(app.apply_mask(source, "99_999_AAAAAAA"), expected)

    def test_case_and_transliteration(self):
        self.assertEqual(app.apply_mask("15_ЦЕФАДИН", "999_Aaaaaaaa"), "015_Tsefadin")
        self.assertEqual(app.apply_mask("15_ЦЕФАДИН", "999_aaaaaaaa"), "015_tsefadin")

    def test_numbers_after_text_are_not_prefix_numbers(self):
        self.assertEqual(app.apply_mask("15_текст 20 от 2026", "99_999_Aaaa"), "015_Teks")
        self.assertEqual(app.apply_mask("15_текст_7", "99_999_Aaaa_99"), "015_Teks_07")

    def test_multiple_words(self):
        self.assertEqual(app.apply_mask("15_Реплевак Оптима", "999_Aaaaaaaa_Aaaaaa"),
                         "015_Replevak_Optima")

    def test_extension_preserved(self):
        self.assertEqual(app.shorten_filename("15_Цефадин.PDF", "999_Aaaaaaaa"), "015_Tsefadin.PDF")

    def test_number_overflow(self):
        with self.assertRaisesRegex(ValueError, "144"):
            app.apply_mask("144_текст", "99_Aaaa")

    def test_invalid_result(self):
        for source, mask in [("!!!.pdf", "AAAA"), ("console.pdf", "AAA"), ("abc.pdf", "999")]:
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    app.shorten_filename(source, mask)


class FileTests(unittest.TestCase):
    def test_first_run_creates_missing_configs(self):
        original_mask = (self.root / "mask.txt").read_bytes()
        code, output = self.run_app()
        self.assertEqual(code, 0)
        self.assertIn("созданы", output)
        self.assertEqual((self.root / "files.txt").read_text(), "")
        self.assertEqual((self.root / "mask.txt").read_bytes(), original_mask)

    def test_init_never_overwrites_user_files(self):
        self.listing("private-example.pdf")
        before = {name: (self.root / name).read_bytes() for name in ("files.txt", "mask.txt")}
        self.assertEqual(self.run_app("--init")[0], 0)
        for name, content in before.items():
            self.assertEqual((self.root / name).read_bytes(), content)

    def test_version_does_not_create_config(self):
        self.file("version.json", '{"version": "1.0.0"}')
        code, output = self.run_app("--version")
        self.assertEqual(code, 0)
        self.assertIn("uRename 1.0.0", output)
        self.assertFalse((self.root / "files.txt").exists())

    def test_instruction_config_preview_and_rename(self):
        first = self.file("3_41_Инструкция Ветацеф.pdf", "original")
        self.listing(first.name)
        (self.root / "mask.txt").write_text(
            "# settings\n!инструкция\n99_999_Aaaaaaaaaa\n", encoding="utf-8-sig")
        code, output = self.run_app("--preview")
        self.assertEqual(code, 0)
        self.assertIn("03_041_Vetatsef.pdf", output)
        self.assertTrue(first.exists())
        self.assertEqual(self.run_app()[0], 0)
        self.assertEqual((self.root / "03_041_Vetatsef.pdf").read_text(), "original")

    def test_instruction_directive_validation_and_disable(self):
        config = self.root / "mask.txt"
        config.write_text("# !инструкция\n999_Aaaa", encoding="utf-8")
        self.assertEqual(app.load_config(str(config)), ("999_Aaaa", False))
        for content in ["!инструкция", "999_Aaaa\n!опечатка"]:
            with self.subTest(content=content):
                config.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    app.load_config(str(config))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="urename_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "mask.txt").write_text("99_999_AAAAAAA\n", encoding="utf-8-sig")

    def file(self, name, content="sample"):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def listing(self, *names):
        (self.root / "files.txt").write_text(
            "\n".join('"' + name + '"' for name in names), encoding="utf-8-sig")

    def run_app(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = app.main(list(args), str(self.root))
        return code, output.getvalue()

    def test_preview_and_real_rename(self):
        first = self.file("11_15_тексттексттекст.pdf", "first")
        second = self.file("15_тексттексттекст.pdf", "second")
        self.listing(first.name, second.name)
        self.assertEqual(self.run_app("--preview")[0], 0)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        self.assertEqual(self.run_app()[0], 0)
        self.assertEqual((self.root / "11_015_TEKSTTE.pdf").read_text(), "first")
        self.assertEqual((self.root / "015_TEKSTTE.pdf").read_text(), "second")
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())

    def test_collision_stops_whole_batch(self):
        first = self.file("1_2_abcdefga.pdf", "first")
        second = self.file("1_2_abcdefgb.pdf", "second")
        self.listing(first.name, second.name)
        self.assertEqual(self.run_app()[0], 1)
        self.assertEqual(first.read_text(), "first")
        self.assertEqual(second.read_text(), "second")
        self.assertFalse((self.root / "01_002_ABCDEFG.pdf").exists())

    def test_occupied_target(self):
        first = self.file("1_2_text.pdf", "first")
        target = self.file("01_002_TEXT.pdf", "existing")
        self.listing(first.name)
        self.assertEqual(self.run_app()[0], 1)
        self.assertEqual(first.read_text(), "first")
        self.assertEqual(target.read_text(), "existing")

    def test_missing_file_stops_whole_batch(self):
        first = self.file("1_2_text.pdf")
        self.listing(first.name, "missing.pdf")
        self.assertEqual(self.run_app()[0], 1)
        self.assertTrue(first.exists())

    def test_folder_rejected(self):
        folder = self.root / "1_2_text"
        folder.mkdir()
        self.listing(folder.name)
        self.assertEqual(self.run_app()[0], 1)
        self.assertTrue(folder.is_dir())

    def test_duplicate_input_renamed_once(self):
        first = self.file("1_2_text.pdf")
        self.listing(first.name, first.name)
        code, output = self.run_app()
        self.assertEqual(code, 0)
        self.assertEqual(output.count("OK:"), 1)

    @unittest.skipUnless(os.name == "nt", "Windows case-insensitive paths")
    def test_case_only_and_repeat_with_updated_list(self):
        first = self.file("01_002_text.pdf")
        self.listing(first.name)
        self.assertEqual(self.run_app()[0], 0)
        self.assertIn("01_002_TEXT.pdf", os.listdir(self.root))
        self.listing("01_002_TEXT.pdf")
        code, output = self.run_app()
        self.assertEqual(code, 0)
        self.assertIn("БЕЗ ИЗМЕНЕНИЙ", output)

    def test_bad_masks(self):
        first = self.file("1_2_text.pdf")
        self.listing(first.name)
        for mask in ["", "___", "99_БББ", "99_Ааа", "99_AA\n999_AA"]:
            with self.subTest(mask=mask):
                (self.root / "mask.txt").write_text(mask, encoding="utf-8")
                self.assertEqual(self.run_app()[0], 1)
                self.assertTrue(first.exists())


if __name__ == "__main__":
    unittest.main()
