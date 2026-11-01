"""
F21 — what the staff assistant has read.

One row is one section of the notes with its embedding. The table is
derived data: index_knowledge rebuilds it from the notes and the
catalogue, so nothing here is ever edited by hand. It holds no customer
records, no prices and no costs (see knowledge.py).
"""

from django.db import models


class KnowledgeChunk(models.Model):
    document = models.CharField(max_length=120)
    title = models.CharField(max_length=200)
    heading = models.CharField(max_length=200)
    text = models.TextField()

    # Shown under an answer, so staff can see where a figure came from
    # and how old it is. Blank for the company's own notes.
    source_url = models.URLField(max_length=500, blank=True)
    checked_on = models.DateField()

    # Lets a rebuild skip what has not changed, and re-embed everything
    # if the embedding model is swapped.
    content_hash = models.CharField(max_length=64)
    embedding = models.JSONField()

    class Meta:
        ordering = ["document", "heading"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "heading"], name="one_chunk_per_document_heading",
            ),
        ]

    def __str__(self):
        return f"{self.title}: {self.heading}"
