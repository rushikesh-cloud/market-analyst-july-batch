import unittest

from app import document_chunking as documents
from app.documents import split_markdown_pages


class ChunkingTests(unittest.TestCase):
    def test_heading_tables_order_and_non_recursive_overlap(self):
        markdown = """# Overview

First paragraph with introductory facts about the annual report, including revenue, operating expenses, cash flow, and the outlook for the coming year.

## Metrics

| Year | Revenue |
| --- | --- |
| 2024 | 100 |
| 2025 | 110 |

Closing paragraph.
"""
        chunks = documents.chunk_markdown(markdown, max_tokens=2000, overlap_tokens=5)
        self.assertEqual([chunk.chunk_type for chunk in chunks], ["para", "table", "para"])
        self.assertEqual(chunks[1].heading_path, ["Overview", "Metrics"])
        self.assertTrue(chunks[1].overlap_text)
        self.assertEqual(
            chunks[1].overlap_text,
            documents._decode(documents._tokens(chunks[0].content)[-5:]),
        )
        self.assertEqual(
            chunks[2].overlap_text,
            documents._decode(documents._tokens(chunks[1].content)[-5:]),
        )
        self.assertEqual([chunk.sequence for chunk in chunks], [0, 1, 2])

    def test_chunk_inputs_respect_token_limit(self):
        markdown = "# Long section\n\n" + "word " * 100
        chunks = documents.chunk_markdown(markdown, max_tokens=30, overlap_tokens=5)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.token_count <= 30 for chunk in chunks))

    def test_html_tables_are_separate_and_paragraphs_share_heading_chunk(self):
        markdown = """# Results

First paragraph.

Second paragraph.

Additional introductory facts about the annual report include revenue, operating expenses, cash flow, and the outlook for the coming year.

<table>
<tr><th>Year</th><th>Revenue</th></tr>
<tr><td>2024</td><td>100</td></tr>
</table>

Closing paragraph.
"""
        chunks = documents.chunk_markdown(markdown)
        self.assertEqual([chunk.chunk_type for chunk in chunks], ["para", "table", "para"])
        self.assertIn("First paragraph.\n\nSecond paragraph.", chunks[0].content)
        self.assertTrue(chunks[1].content.startswith("<table>"))

    def test_page_breaks_assign_chunks_and_preserve_heading_context(self):
        markdown = """# Results

Page one text includes introductory facts about the annual report, including revenue, operating expenses, cash flow, and the outlook for the coming year.

<!-- PageBreak -->

Page two text.
"""
        chunks = documents.chunk_markdown(markdown)
        self.assertEqual([chunk.page_number for chunk in chunks], [1, 2])
        self.assertEqual(chunks[1].heading_path, ["Results"])
        self.assertEqual(
            split_markdown_pages(markdown),
            [markdown.split("<!-- PageBreak -->")[0].strip(), "Page two text."],
        )

    def test_short_content_merges_forward_and_rebuilds_all_overlap(self):
        prior = " ".join(["prior"] * 70)
        short = " ".join(["brief"] * 19)
        following = " ".join(["next"] * 20)
        last = " ".join(["last"] * 30)
        markdown = f"# Prior\n{prior}\n# Brief\n{short}\n# Next\n{following}\n# Last\n{last}"

        chunks = documents.chunk_markdown(markdown)

        self.assertEqual([chunk.content for chunk in chunks], [prior, f"{short}\n\n{following}", last])
        self.assertEqual(chunks[1].heading_path, ["Next"])
        self.assertEqual([chunk.sequence for chunk in chunks], [0, 1, 2])
        for index, chunk in enumerate(chunks):
            expected_overlap = documents._decode(documents._tokens(chunks[index - 1].content)[-50:]) if index else ""
            self.assertEqual(chunk.overlap_text, expected_overlap)
            embedding_input = "\n".join(value for value in (
                " > ".join(chunk.heading_path), expected_overlap, chunk.content
            ) if value)
            self.assertEqual(chunk.token_count, len(documents._tokens(embedding_input)))

    def test_consecutive_short_chunks_merge_into_following_chunk(self):
        body = " ".join(["body"] * 25)
        chunks = documents.chunk_markdown(f"# One\nBrief.\n# Two\nAlso brief.\n# Three\n{body}")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].content, f"Brief.\n\nAlso brief.\n\n{body}")
        self.assertEqual(chunks[0].overlap_text, "")

    def test_exactly_twenty_content_tokens_do_not_merge(self):
        body = " ".join(["word"] * 20)
        self.assertEqual(len(documents._tokens(body)), 20)
        chunks = documents.chunk_markdown(f"# One\n{body}\n# Two\n{body}")
        self.assertEqual([chunk.content for chunk in chunks], [body, body])

    def test_last_short_chunk_is_preserved(self):
        body = " ".join(["word"] * 25)
        chunks = documents.chunk_markdown(f"# One\n{body}\n# Two\nEnd.")
        self.assertEqual([chunk.content for chunk in chunks], [body, "End."])
        self.assertEqual(documents.chunk_markdown("End.")[0].content, "End.")
        self.assertEqual(documents.chunk_markdown(""), [])

    def test_merge_keeps_destination_page_and_table_metadata(self):
        table = "| Year | Revenue |\n| --- | --- |\n| 2024 | 100 |"
        chunks = documents.chunk_markdown(f"# Overview\nBrief.\n<!-- PageBreak -->\n## Metrics\n{table}")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].content, f"Brief.\n\n{table}")
        self.assertEqual(chunks[0].page_number, 2)
        self.assertEqual(chunks[0].heading_path, ["Overview", "Metrics"])
        self.assertEqual(chunks[0].chunk_type, "table")

    def test_merge_is_skipped_if_it_would_exceed_token_limit(self):
        short = " ".join(["brief"] * 19)
        following = " ".join(["word"] * 22)
        chunks = documents.chunk_markdown(f"# One\n{short}\n# Two\n{following}", max_tokens=30, overlap_tokens=5)
        self.assertEqual([chunk.content for chunk in chunks], [short, following])
        self.assertTrue(all(chunk.token_count <= 30 for chunk in chunks))

    def test_short_tail_of_split_paragraph_merges_forward(self):
        body = " ".join(["word"] * 55)
        following = " ".join(["next"] * 25)
        chunks = documents.chunk_markdown(f"# One\n{body}\n# Two\n{following}", max_tokens=60, overlap_tokens=5)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[1].content, f"word word word\n\n{following}")
        self.assertEqual(" ".join(" ".join(chunk.content for chunk in chunks).split()), f"{body} {following}")
        self.assertTrue(all(chunk.token_count <= 60 for chunk in chunks))

    def test_zero_overlap_stays_empty_after_merging(self):
        body = " ".join(["word"] * 25)
        chunks = documents.chunk_markdown(f"# One\n{body}\n# Two\nBrief.\n# Three\n{body}", overlap_tokens=0)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(chunk.overlap_text == "" for chunk in chunks))
