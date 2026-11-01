"""
Loads the notes and the catalogue into the assistant (F21).

    manage.py index_knowledge

Run it after editing a note in apps/assistant/knowledge, or after changing
the catalogue, the warranty policies or the subsidy rules. Only what
changed is embedded again, so running it twice is harmless.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.assistant import knowledge, ollama


class Command(BaseCommand):
    help = "Loads the assistant's notes and the catalogue into the search index."

    def handle(self, *args, **options):
        try:
            result = knowledge.rebuild_index()
        except ollama.OllamaUnavailable as exc:
            raise CommandError(
                f"{exc}. Start Ollama and check the embedding model is pulled. "
                "The existing index has not been changed."
            ) from exc

        self.stdout.write(self.style.SUCCESS(
            f"{result['sections']} sections: {result['embedded']} embedded, "
            f"{result['removed']} removed."
        ))
