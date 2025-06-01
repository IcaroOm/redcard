import tempfile
import os
import sqlite3
import zipfile
import json
from django.db import transaction
from .models import Deck, Card 

class AnkiImportError(Exception):
    pass

class AnkiImporterService:
    def __init__(self, user):
        self.user = user
        self._tmp_apkg_path = None
        self._tmp_db_path = None

    def _cleanup_temp_files(self):
        if self._tmp_apkg_path and os.path.exists(self._tmp_apkg_path):
            os.unlink(self._tmp_apkg_path)
        if self._tmp_db_path and os.path.exists(self._tmp_db_path):
            os.unlink(self._tmp_db_path)

    def _validate_models_and_get_specs(self, models_json_str: str) -> list:
        models_data = json.loads(models_json_str)
        valid_model_specs = []
        
        required_anki_fields = {
            'character':   ['hanzi', 'character', 'simplified', 'zi', 'chinese', 'expression', 'front'],
            'pinyin':      ['pinyin', 'pronunciation', 'reading'],
            'translation': ['english', 'translation', 'meaning', 'definition', 'back'],
        }

        for anki_model_id_str, anki_model_config in models_data.items():
            model_field_names = [fld['name'].lower() for fld in anki_model_config.get('flds', [])]

            actual_fields = [fld['name'] for fld in anki_model_config.get('flds', [])]
            print(f"[DEBUG] Checking model {anki_model_id_str}, fields = {actual_fields}")

            current_model_field_map = {}
            all_required_found = True

            for target_field, variations in required_anki_fields.items():
                found_variation_for_target = False
                for anki_field_idx, anki_field_name_lower in enumerate(model_field_names):
                    if anki_field_name_lower in variations:
                        current_model_field_map[target_field] = anki_field_idx
                        found_variation_for_target = True
                        break
                if not found_variation_for_target:
                    all_required_found = False
                    break
            
            if all_required_found:
                try:
                    valid_model_specs.append({
                        'model_id': int(anki_model_id_str),
                        'field_map': current_model_field_map
                    })
                except ValueError:
                    pass 

        print("[DEBUG] valid_model_specs before returning:", valid_model_specs)
        return valid_model_specs

    def _create_card_from_note(self, note_row_data: sqlite3.Row, deck_instance: Deck, valid_model_specs_map: dict):
        note_fields = note_row_data['flds'].split('\x1f')
        anki_note_model_id = int(note_row_data['mid'])

        model_spec = valid_model_specs_map.get(anki_note_model_id)
        if not model_spec:
            return

        field_map = model_spec['field_map']
        try:
            character_val   = note_fields[field_map['character']].strip()
            pinyin_val      = note_fields[field_map['pinyin']].strip()
            translation_val = note_fields[field_map['translation']].strip()
        except (IndexError, KeyError):
            return

        if not character_val or not pinyin_val:
            return

        Card.objects.create(
            deck=deck_instance,
            character=character_val,
            pinyin=pinyin_val,
            translation=translation_val
        )

    def import_deck_from_file(self, anki_file_obj) -> Deck:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.apkg') as tmp_apkg:
                for chunk in anki_file_obj.chunks():
                    tmp_apkg.write(chunk)
                self._tmp_apkg_path = tmp_apkg.name

            db_filename_in_zip = None
            with zipfile.ZipFile(self._tmp_apkg_path, 'r') as zip_ref:
                for name in zip_ref.namelist():
                    base = os.path.basename(name)
                    if base in ("collection.anki2", "collection.anki21"):
                        db_filename_in_zip = name
                        break
                if not db_filename_in_zip:
                    raise AnkiImportError("Invalid Anki package: Missing the main collection DB (collection.anki2 or .anki21).")
                
                print(f"[DEBUG] extracting DB from .apkg → {db_filename_in_zip}")
                with tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite') as tmp_db:
                    tmp_db.write(zip_ref.read(db_filename_in_zip))
                    self._tmp_db_path = tmp_db.name

            print(f"[DEBUG] tmp_db_path = {self._tmp_db_path!r}")

            conn = sqlite3.connect(self._tmp_db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [tup[0] for tup in cursor.fetchall()]
            print("[DEBUG] tables in extracted DB:", tables)
            if "col" in tables:
                cursor.execute("PRAGMA table_info(col);")
                print("[DEBUG] col schema:", cursor.fetchall())
            else:
                conn.close()
                raise AnkiImportError("After extraction, no 'col' table was found.")

            cursor.execute("SELECT models FROM col LIMIT 1")
            col_table_row = cursor.fetchone()
            print("[DEBUG] fetched col row:", col_table_row)

            if col_table_row is None:
                print("[DEBUG] col_table_row is None (no rows in col)")
                conn.close()
                raise AnkiImportError("Invalid Anki package: 'col' table is empty.")
            else:
                print("[DEBUG] col_table_row keys:", list(col_table_row.keys()))
                try:
                    raw_models = col_table_row["models"]
                except KeyError:
                    print("[DEBUG] 'models' not found in this row at all!")
                    conn.close()
                    raise AnkiImportError("Invalid Anki package: 'models' column is missing.")

                if raw_models is None:
                    print("[DEBUG] col_table_row['models'] is None")
                    conn.close()
                    raise AnkiImportError("Invalid Anki package: 'models' column is NULL.")
                elif raw_models == "":
                    print("[DEBUG] col_table_row['models'] is an empty string")
                    conn.close()
                    raise AnkiImportError("Invalid Anki package: 'models' column is empty.")
                else:
                    print("[DEBUG] col_table_row['models'] (first 200 chars):")
                    print(raw_models[:200])

                    try:
                        full_models = json.loads(raw_models)
                        print("[DEBUG] top‐level model IDs in JSON:", list(full_models.keys())[:5], "…")
                        for mid_str, model_conf in full_models.items():
                            actual_fields = [fld["name"] for fld in model_conf.get("flds", [])]
                            print(f"[DEBUG]  • Model {mid_str} ⇒ fields: {actual_fields}")
                    except Exception as e:
                        print(f"[DEBUG] ERROR decoding JSON in 'models': {e}")
                        conn.close()
                        raise AnkiImportError("Invalid Anki package: 'models' is not valid JSON.")

            valid_model_specs_list = self._validate_models_and_get_specs(raw_models)
            if not valid_model_specs_list:
                conn.close()
                raise AnkiImportError(
                    "No compatible Anki card models found. "
                    "Ensure your notes have fields for Hanzi/Character, Pinyin, and English/Translation."
                )

            valid_model_specs_map = {spec['model_id']: spec for spec in valid_model_specs_list}
            anki_model_ids_to_query = list(valid_model_specs_map.keys())

            placeholders = ','.join(['?'] * len(anki_model_ids_to_query))
            cursor.execute(
                f"SELECT mid, flds FROM notes WHERE mid IN ({placeholders})",
                anki_model_ids_to_query
            )
            anki_notes_data = cursor.fetchall()
            conn.close()

            if not anki_notes_data:
                raise AnkiImportError("No notes found matching the compatible card models.")

            deck_name = os.path.splitext(os.path.basename(anki_file_obj.name))[0]
            created_deck = None
            with transaction.atomic():
                created_deck = Deck.objects.create(user=self.user, name=deck_name)

                for note_row in anki_notes_data:
                    self._create_card_from_note(note_row, created_deck, valid_model_specs_map)

                if created_deck.cards.count() == 0:
                    raise AnkiImportError(
                        f"No cards could be created for deck '{deck_name}'. "
                        "This might be due to all notes missing required fields or an issue with field mappings."
                    )

            return created_deck

        except AnkiImportError:
            raise
        except zipfile.BadZipFile:
            raise AnkiImportError("Invalid Anki package: The uploaded file is not a valid .apkg (zip) file.")
        except sqlite3.Error as db_err:
            print(f"[DEBUG] SQLite error: {db_err}")
            raise AnkiImportError(f"Database error while processing Anki file: {db_err}")
        except Exception as e:
            print(f"[DEBUG] Unexpected error during Anki import: {e}")
            raise AnkiImportError("An unexpected error occurred while processing the Anki deck.") from e
        finally:
            self._cleanup_temp_files()
