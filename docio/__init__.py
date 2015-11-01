import abc
import os
import shutil
import zipfile

from typing import List, Optional

import lxml.etree


class IOBase(metaclass=abc.ABCMeta):
    def __init__(self, file_path: str, *args, **kwargs) -> None:
        self.original_path = file_path

    @abc.abstractmethod
    def extract(self) -> List[str]:
        """Return list of paragraph.
        """
        ...

    @abc.abstractmethod
    def swap(self, texts: List[str]) -> None:
        ...

    @abc.abstractmethod
    def save(self, dest_file_path: str=None) -> None:
        """
        :param dest_file_path: When this parameter is None, overwrite the original file.
        """
        ...

    def _make_parent_directory(self, file_path: str) -> None:
        """Make directories for the file_path.
        """
        directory = os.path.dirname(file_path)
        if not os.path.exists(directory):
            os.makedirs(directory)


class TextIO(IOBase):
    def __init__(self, file_path: str, *args, **kwargs) -> None:
        super().__init__(file_path)
        with open(file_path) as f:
            self.text = f.read()

    def extract(self) -> List[str]:
        return [self.text]

    def swap(self, texts: List[str]) -> None:
        self.text = texts[0]

    def save(self, dest_file_path: str=None) -> None:
        actual_dest_file_path = self.original_path if dest_file_path is None else dest_file_path
        self._make_parent_directory(actual_dest_file_path)
        with open(actual_dest_file_path, 'w') as f:
            f.write(self.text)


class OfficeOpenXMLSpreadsheetIO(IOBase):
    """As know as Excel.
    """
    namespaces = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    shared_strings_path = 'xl/sharedStrings.xml'

    def __init__(self, file_path: str, *args, **kwargs) -> None:
        super().__init__(file_path)
        # Read strings file from the orifinal file. OfficeOpenXML file is compressed as zip.
        with zipfile.ZipFile(file_path, 'r') as zip_file:
            with zip_file.open(self.shared_strings_path) as zip_element:
                shared_strings = zip_element.read()  # type: bytes
        self.etree = lxml.etree.fromstring(shared_strings)

    def extract(self) -> List[str]:
        return self.etree.xpath('//ns:t/text()', namespaces=self.namespaces)

    def swap(self, texts: List[str]) -> None:
        for t, new_text in zip(self.etree.xpath('//ns:t', namespaces=self.namespaces), texts):
            if new_text is not None:
                t.text = new_text

    def save(self, dest_file_path: str=None) -> None:
        if dest_file_path is None:
            actual_dest_file_path = self.original_path
        else:
            self._make_parent_directory(dest_file_path)
            shutil.copyfile(self.original_path, dest_file_path)
            actual_dest_file_path = dest_file_path

        shared_strings = lxml.etree.tostring(self.etree, xml_declaration=True, encoding='UTF-8')
        with zipfile.ZipFile(actual_dest_file_path, 'a') as zip_file:
            zip_file.writestr(self.shared_strings_path, shared_strings)


class XMLIO(IOBase):
    def __init__(self, file_path: str, *args, **kwargs) -> None:
        super().__init__(file_path)
        with open(file_path) as f:
            self.etree = lxml.etree.parse(f)

    def extract(self) -> List[str]:
        def append_if_not_only_whitespace(text: Optional[str], texts: List[str]) -> List[str]:
            if text is not None and text.strip() != '':
                texts.append(text)
            return texts

        def extract(element: lxml.etree._Element, texts: List[str]) -> List[str]:
            texts = append_if_not_only_whitespace(element.text, texts)
            for child_element in element.iterchildren():
                texts = extract(child_element, texts)
            return append_if_not_only_whitespace(element.tail, texts)
        return extract(self.etree.getroot(), [])

    def swap(self, texts: List[str]) -> None:
        def swap_if_valid(
                element: lxml.etree._Element, property: str, texts: List[str]) -> List[str]:
            text = getattr(element, property)
            if text is not None and text.strip() != '':
                new_text = texts.pop()
                if new_text is not None:
                    setattr(element, property, new_text)
            return texts

        def swap(element: lxml.etree._Element, texts: List[str]) -> List[str]:
            texts = swap_if_valid(element, 'text', texts)
            for child_element in element.iterchildren():
                texts = swap(child_element, texts)
            return swap_if_valid(element, 'tail', texts)

        swap(self.etree.getroot(), list(reversed(texts)))

    def save(self, dest_file_path: str=None) -> None:
        if dest_file_path is None:
            actual_dest_file_path = self.original_path
        else:
            self._make_parent_directory(dest_file_path)
            actual_dest_file_path = dest_file_path

        dest_xml = lxml.etree.tostring(self.etree, xml_declaration=True, encoding='UTF-8')
        with open(actual_dest_file_path, 'wb') as f:
            f.write(dest_xml)
