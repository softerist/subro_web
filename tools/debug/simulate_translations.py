"""
Script to simulate translation jobs and insert test records into the database.
Run this inside the API container: docker exec -it subapp_dev-api-1 python /app/simulate_translations.py
"""

from datetime import UTC, datetime

from app.db.models.translation_log import TranslationLog

# Setup database connection
from app.db.session import SyncSessionLocal


def simulate_translations():
    """Insert simulated translation records into the database."""

    simulations = [
        {
            "file_name": "/mnt/media/Movies/Test Movie (2024)/Test.Movie.2024.en.srt",
            "source_language": "en",
            "target_language": "ro",
            "service_used": "deepl",
            "characters_billed": 15420,
            "deepl_characters": 15420,
            "google_characters": 0,
            "status": "success",
            "output_file_path": "/mnt/media/Movies/Test Movie (2024)/Test.Movie.2024.ro.srt",
        },
        {
            "file_name": "/mnt/media/TV Shows/Test Show S01/Test.Show.S01E01.en.srt",
            "source_language": "en",
            "target_language": "ro",
            "service_used": "google",
            "characters_billed": 12850,
            "deepl_characters": 0,
            "google_characters": 12850,
            "status": "success",
            "output_file_path": "/mnt/media/TV Shows/Test Show S01/Test.Show.S01E01.ro.srt",
        },
        {
            "file_name": "/mnt/media/Movies/Another Movie (2023)/Another.Movie.2023.en.srt",
            "source_language": "en",
            "target_language": "ro",
            "service_used": "mixed",
            "characters_billed": 25000,
            "deepl_characters": 15000,
            "google_characters": 10000,
            "status": "success",
            "output_file_path": "/mnt/media/Movies/Another Movie (2023)/Another.Movie.2023.ro.srt",
        },
    ]

    with SyncSessionLocal() as db:
        for sim in simulations:
            log_entry = TranslationLog(timestamp=datetime.now(UTC), **sim)
            db.add(log_entry)
            print(
                f"✓ Added: {sim['file_name'].split('/')[-1]} ({sim['service_used']}, {sim['characters_billed']} chars)"
            )

        db.commit()
        print(
            f"\n✅ Successfully inserted {len(simulations)} simulated translation records!"
        )
        print("   Refresh the Settings page to see the statistics.")


if __name__ == "__main__":
    simulate_translations()
