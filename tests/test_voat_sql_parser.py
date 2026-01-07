"""
ABOUTME: Tests for VoatSQLParser state machine
ABOUTME: Covers escape sequences, NULL handling, and edge cases
"""

import pytest
import tempfile
import gzip
from core.importers.voat_sql_parser import VoatSQLParser


class TestVoatSQLParser:
    """Test suite for VoatSQLParser."""

    def setup_method(self):
        """Create parser instance for each test."""
        self.parser = VoatSQLParser()

    def test_parse_simple_values(self):
        """Test parsing simple values without escapes."""
        values, end = self.parser._parse_values_tuple("(1,'hello',NULL)", 0)
        assert values == [1, 'hello', None]

    def test_parse_escaped_quote(self):
        """Test parsing backslash-escaped single quote."""
        values, end = self.parser._parse_values_tuple("(1,'don\\'t')", 0)
        assert values == [1, "don't"]

    def test_parse_doubled_quote(self):
        """Test parsing MySQL doubled-quote escape."""
        values, end = self.parser._parse_values_tuple("(1,'it''s')", 0)
        assert values == [1, "it's"]

    def test_parse_escaped_backslash(self):
        """Test parsing escaped backslash."""
        values, end = self.parser._parse_values_tuple("(1,'path\\\\to\\\\file')", 0)
        assert values == [1, "path\\to\\file"]

    def test_parse_escaped_newline(self):
        """Test parsing escaped newline."""
        values, end = self.parser._parse_values_tuple("(1,'line1\\nline2')", 0)
        assert values == [1, "line1\nline2"]

    def test_parse_escaped_carriage_return(self):
        """Test parsing escaped carriage return."""
        values, end = self.parser._parse_values_tuple("(1,'text\\r\\nhere')", 0)
        assert values == [1, "text\r\nhere"]

    def test_parse_null_value(self):
        """Test parsing NULL value."""
        values, end = self.parser._parse_values_tuple("(NULL,'text',NULL)", 0)
        assert values == [None, 'text', None]

    def test_parse_integer(self):
        """Test parsing integer values."""
        values, end = self.parser._parse_values_tuple("(123,456,-789)", 0)
        assert values == [123, 456, -789]

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        values, end = self.parser._parse_values_tuple("(1,'')", 0)
        assert values == [1, '']

    def test_parse_value_with_comma(self):
        """Test parsing string containing comma."""
        values, end = self.parser._parse_values_tuple("(1,'hello, world')", 0)
        assert values == [1, 'hello, world']

    def test_parse_value_with_parentheses(self):
        """Test parsing string containing parentheses."""
        values, end = self.parser._parse_values_tuple("(1,'func(x)')", 0)
        assert values == [1, 'func(x)']

    def test_parse_datetime(self):
        """Test parsing datetime string."""
        values, end = self.parser._parse_values_tuple("(1,'2013-11-08 12:00:00')", 0)
        assert values == [1, '2013-11-08 12:00:00']

    def test_parse_html_content(self):
        """Test parsing HTML content with special chars."""
        values, end = self.parser._parse_values_tuple("(1,'<p>Hello &amp; goodbye</p>')", 0)
        assert values == [1, '<p>Hello &amp; goodbye</p>']

    def test_column_maps_exist(self):
        """Test that column maps are defined."""
        assert 'submission' in self.parser.COLUMN_MAPS
        assert 'comment' in self.parser.COLUMN_MAPS
        assert len(self.parser.COLUMN_MAPS['submission']) == 27
        assert len(self.parser.COLUMN_MAPS['comment']) == 22

    def test_unknown_table_raises_error(self):
        """Test that unknown table name raises ValueError."""
        with tempfile.NamedTemporaryFile(suffix='.sql.gz', delete=False) as f:
            with gzip.open(f.name, 'wt') as gz:
                gz.write("INSERT INTO `unknown` VALUES (1);")

            with pytest.raises(ValueError, match="Unknown table"):
                list(self.parser.stream_rows(f.name, 'unknown'))


class TestVoatSQLParserIntegration:
    """Integration tests with sample SQL data."""

    def setup_method(self):
        self.parser = VoatSQLParser()

    def create_test_file(self, sql_content):
        """Create a gzipped SQL file with given content."""
        f = tempfile.NamedTemporaryFile(suffix='.sql.gz', delete=False)
        with gzip.open(f.name, 'wt', encoding='utf-8') as gz:
            gz.write(sql_content)
        return f.name

    def test_parse_submission_insert(self):
        """Test parsing a realistic submission INSERT."""
        sql = """
        -- MariaDB dump
        INSERT INTO `submission` VALUES (34,NULL,59,'','2013-11-08 12:00:00',NULL,0,'',0,0,0,NULL,'voatdev',68,'','Checking out the date time thingy...','Text',68,NULL,'Atko',1966,NULL,NULL,NULL,2,'2017-01-18 10:02:41',0);
        """
        file_path = self.create_test_file(sql)

        rows = list(self.parser.stream_rows(file_path, 'submission'))
        assert len(rows) == 1

        row = rows[0]
        assert row['submissionid'] == 34
        assert row['subverse'] == 'voatdev'
        assert row['userName'] == 'Atko'
        assert row['title'] == 'Checking out the date time thingy...'
        assert row['sum'] == 68

    def test_parse_comment_insert(self):
        """Test parsing a realistic comment INSERT."""
        sql = """
        INSERT INTO `comment` VALUES (4,'True. Just tried this.','2013-11-20 17:43:00',0,'<p>True. Just tried this.</p>',0,0,0,0,0,0,0,NULL,0,73,'TODO',1,1,'Atko',0,4,'2020-02-07 01:49:36');
        """
        file_path = self.create_test_file(sql)

        rows = list(self.parser.stream_rows(file_path, 'comment'))
        assert len(rows) == 1

        row = rows[0]
        assert row['commentid'] == 4
        assert row['content'] == 'True. Just tried this.'
        assert row['userName'] == 'Atko'
        assert row['subverse'] == 'TODO'
        assert row['parentid'] == 0
        assert row['submissionid'] == 73

    def test_parse_multi_row_insert(self):
        """Test parsing INSERT with multiple rows."""
        sql = """
        INSERT INTO `submission` VALUES (1,NULL,0,'','2013-01-01 00:00:00',NULL,0,'',0,0,0,NULL,'test1',10,'','Title 1','Text',10,NULL,'user1',100,NULL,NULL,NULL,0,'2020-01-01 00:00:00',0),(2,NULL,0,'','2013-01-02 00:00:00',NULL,0,'',0,0,0,NULL,'test2',20,'','Title 2','Link',20,NULL,'user2',200,NULL,NULL,NULL,0,'2020-01-01 00:00:00',0);
        """
        file_path = self.create_test_file(sql)

        rows = list(self.parser.stream_rows(file_path, 'submission'))
        assert len(rows) == 2

        assert rows[0]['submissionid'] == 1
        assert rows[0]['subverse'] == 'test1'

        assert rows[1]['submissionid'] == 2
        assert rows[1]['subverse'] == 'test2'

    def test_parse_escaped_content(self):
        """Test parsing content with escaped characters."""
        sql = """
        INSERT INTO `comment` VALUES (1,'I don\\'t think so','2020-01-01 00:00:00',0,'<p>I don\\'t think so</p>',0,0,0,0,0,0,0,NULL,0,1,'test',1,1,'user',0,0,'2020-01-01 00:00:00');
        """
        file_path = self.create_test_file(sql)

        rows = list(self.parser.stream_rows(file_path, 'comment'))
        assert len(rows) == 1
        assert rows[0]['content'] == "I don't think so"

    def test_skip_comments_and_metadata(self):
        """Test that SQL comments and metadata are skipped."""
        sql = """
        -- MariaDB dump 10.19
        /*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
        DROP TABLE IF EXISTS `submission`;
        CREATE TABLE `submission` (id INT);
        LOCK TABLES `submission` WRITE;
        INSERT INTO `submission` VALUES (1,NULL,0,'','2020-01-01 00:00:00',NULL,0,'',0,0,0,NULL,'test',10,'','Title','Text',10,NULL,'user',100,NULL,NULL,NULL,0,'2020-01-01 00:00:00',0);
        UNLOCK TABLES;
        """
        file_path = self.create_test_file(sql)

        rows = list(self.parser.stream_rows(file_path, 'submission'))
        assert len(rows) == 1
        assert rows[0]['submissionid'] == 1
