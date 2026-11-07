"""Compare parsing/rendering to the pre-optimization behavior, not new expectations."""
import copy
import unittest
from unittest import mock
from bs4 import BeautifulSoup
from PyQt6 import QtCore, QtGui
import pr_test_support as navigation
from nexus import graphics, text_processing


def legacy_summary(source):
    has_text = bool(BeautifulSoup(source, 'html.parser').get_text(strip=True))
    soup = BeautifulSoup(source, 'html.parser')
    for element in soup(['head', 'style', 'script']):
        element.decompose()
    for element in soup.find_all('br'):
        element.replace_with('\n')
    for element in soup.find_all(['p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        element.insert_after('\n')
    title = next((' '.join(line.split()) for line in soup.get_text().splitlines() if line.split()), '')
    return title, has_text


def legacy_normalize(source):
    soup = BeautifulSoup(source, 'html.parser')
    body = soup.find('body')
    if body is None:
        body = soup
    for paragraph in body.find_all('p'):
        del paragraph['style']
    result = body.encode_contents().decode('utf-8').strip()
    return '' if result == '<p><br/></p>' else result


SOURCES = [
    '', '  \n \t', 'First line\nSecond line', 'Spacing  and\t tabs',
    'α β ∫ x → y', 'nonbreaking\u00a0space', 'R&D &amp; &lt; &gt; &#169;',
    'less < than and > greater', '<p>Unclosed <b>bold',
    '<html><head><title>Metadata title</title><style>p{color:red}</style></head><body><p>Visible</p></body></html>',
    '<script>hidden()</script><style>body{color:red}</style><p>Text</p>',
    '<p>First <b>bold</b> &amp; <i>italic</i></p><p>Second</p>',
    '<div><h1>Heading</h1><ul><li>One</li><li>Two</li></ul></div>',
    '<p><br/></p><p>Next<br/>Line</p>', '<!--comment--><p></p>',
    '<a href="https://example.org">Link</a>', '<p style="color:red">Color</p>',
]


class TextSummaryTests(unittest.TestCase):
    def setUp(self):
        text_processing.clear_caches()

    def test_titles_and_thumbnail_decisions_match_legacy(self):
        for source in SOURCES:
            with self.subTest(source=source):
                self.assertEqual(text_processing.source_summary(source), legacy_summary(source))
                self.assertEqual(text_processing.source_summary(source), legacy_summary(source))

    def test_plain_labels_need_no_html_parser(self):
        with mock.patch.object(text_processing, 'BeautifulSoup', side_effect=AssertionError('parsed plain text')):
            self.assertEqual(text_processing.source_summary('Hello\nworld'), ('Hello', True))
            self.assertEqual(text_processing.source_summary(' \n '), ('', False))


    def test_current_source_is_key_and_old_results_are_immutable(self):
        a = text_processing.source_summary('<p>Before</p>')
        b = text_processing.source_summary('<p>After</p>')
        self.assertEqual(a, ('Before', True))
        self.assertEqual(b, ('After', True))
        self.assertEqual(text_processing.source_summary('<p>Before</p>'), a)

    def test_cache_is_bounded_and_large_documents_are_not_retained(self):
        for i in range(text_processing.CACHE_SIZE + 20):
            text_processing.source_summary(f'Label {i}')
            text_processing.normalize_html(f'<p style="color:red">Label {i}</p>')
        self.assertLessEqual(text_processing._cached_summary.cache_info().currsize, text_processing.CACHE_SIZE)
        self.assertLessEqual(text_processing._cached_normalized.cache_info().currsize, text_processing.CACHE_SIZE)
        text_processing.clear_caches()
        source = '<p>' + 'Large text ' * text_processing.MAX_CACHED_SOURCE + '</p>'
        self.assertEqual(text_processing.source_summary(source), legacy_summary(source))
        self.assertEqual(text_processing.normalize_html(source), legacy_normalize(source))
        self.assertEqual(text_processing._cached_summary.cache_info().currsize, 0)
        self.assertEqual(text_processing._cached_normalized.cache_info().currsize, 0)

    def test_html_cleanup_matches_legacy_byte_for_byte_and_reuses_results(self):
        for source in SOURCES:
            self.assertEqual(text_processing.normalize_html(source), legacy_normalize(source))
        text_processing.clear_caches()
        with mock.patch.object(text_processing, 'BeautifulSoup', wraps=BeautifulSoup) as parser:
            source = '<html><body><p style="margin-top:0px"><b>Text</b></p></body></html>'
            first = text_processing.normalize_html(source)
            self.assertEqual(text_processing.normalize_html(source), first)
            self.assertEqual(parser.call_count, 1)


class TextRenderingTests(unittest.TestCase):
    setUpClass = classmethod(navigation.MapTestCase.setUpClass.__func__)
    tearDownClass = classmethod(navigation.MapTestCase.tearDownClass.__func__)
    setUp = navigation.MapTestCase.setUp
    tearDown = navigation.MapTestCase.tearDown
    node = navigation.MapTestCase.node
    child = navigation.MapTestCase.child
    select = navigation.MapTestCase.select
    key = navigation.MapTestCase.key

    def text(self):
        return next(item for item in self.root.leaf.childItems() if isinstance(item, graphics.TextItem))

    def rendered(self):
        item = self.text()
        formats = []
        cursor = QtGui.QTextCursor(item.document())
        for i in range(item.document().characterCount()-1):
            cursor.setPosition(i)
            cursor.setPosition(i+1, QtGui.QTextCursor.MoveMode.KeepAnchor)
            fmt = cursor.charFormat()
            formats.append((fmt.font().toString(), fmt.foreground().color().name(),
                            fmt.background().color().name(), fmt.anchorHref()))
        rect = self.root.sceneBoundingRect()
        image = QtGui.QImage(700, 300, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtGui.QColor('white'))
        painter = QtGui.QPainter(image)
        self.scene.render(painter, QtCore.QRectF(0, 0, 700, 300), rect)
        painter.end()
        pixels = image.constBits().asstring(image.sizeInBytes())
        return item.toPlainText(), item.getSrc(), item.DefaultFont.toString(), item.boundingRect(), formats, pixels

    def test_fonts_formatting_links_bounds_and_pixels_match_legacy_without_saves(self):
        uid = next(iter(self.root.node['content']))
        for source in SOURCES:
            with self.subTest(source=source):
                value = self.root.node['content'][uid]
                value.update(source=source, font_family='Helvetica', font_size=17,
                    color='#25496d', maxwidth=150)
                self.root.node.keyChanged('content')
                self.root.node.save()
                self.graph.clearchanges()
                saved = copy.deepcopy(self.graph.getuid(self.root.node['uid'])['content'])
                with mock.patch.object(graphics, 'normalize_html', legacy_normalize):
                    self.root.renew()
                    before = self.rendered()
                self.root.renew()
                after = self.rendered()
                self.assertEqual(before, after)
                self.assertEqual(self.graph.getuid(self.root.node['uid'])['content'], saved)
                self.assertFalse(self.graph.lastchanges())

    def test_edit_font_color_and_undo_do_not_reuse_stale_cleanup(self):
        item = self.text()
        old = item.getSrc()
        item.setHtml('<p>Changed <b>bold</b> <a href="https://example.org">link</a></p>')
        item.setFont(QtGui.QFont('Helvetica', 22))
        item.setDefaultTextColor(QtGui.QColor('red'))
        self.assertNotEqual(item.getSrc(), old)
        self.assertEqual(item.getSrc(), legacy_normalize(item.document().toHtml().strip()))
        item.mode = item.EditSourceMode
        item.setPlainText('<p><i>Source edit</i></p>')
        self.assertEqual(item.getSrc(), legacy_normalize(item.toPlainText().strip()))
        item.setStaticMode()
        self.assertEqual(item.toPlainText(), 'Source edit')

