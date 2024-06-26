"""Markdown Treeprocessors."""
from __future__ import absolute_import
from __future__ import unicode_literals

from . import inlinepatterns
from . import odict
from . import util


def build_treeprocessors(md_instance, **kwargs):
    """Build the default treeprocessors for Markdown."""
    treeprocessors = odict.OrderedDict()
    treeprocessors["inline"] = InlineProcessor(md_instance)
    treeprocessors["prettify"] = PrettifyTreeprocessor(md_instance)
    return treeprocessors


def isString(s):
    """Check if it's string."""
    if not isinstance(s, util.AtomicString):
        return isinstance(s, util.string_type)
    return False


class Treeprocessor(util.Processor):
    """Treeprocessors are run on the ElementTree object before serialization.

    Each Treeprocessor implements a "run" method that takes a pointer to an
    ElementTree, modifies it as necessary and returns an ElementTree
    object.

    Treeprocessors must extend markdown.Treeprocessor.

    """
    def run(self, root):
        """Main treeprocessor method.

        Subclasses of Treeprocessor should implement a `run` method, which
        takes a root ElementTree. This method can return another ElementTree
        object, and the existing root ElementTree will be replaced, or it can
        modify the current tree and return None.
        """
        pass  # pragma: no cover


class InlineProcessor(Treeprocessor):
    """A Treeprocessor that traverses a tree, applying inline patterns."""

    def __init__(self, md):
        self.__placeholder_prefix = util.INLINE_PLACEHOLDER_PREFIX
        self.__placeholder_suffix = util.ETX
        self.__placeholder_length = 4 + len(self.__placeholder_prefix) \
                                      + len(self.__placeholder_suffix)
        self.__placeholder_re = util.INLINE_PLACEHOLDER_RE
        self.markdown = md
        self.inlinePatterns = md.inlinePatterns

    def __makePlaceholder(self, type):
        """Generate a placeholder."""
        id = "%04d" % len(self.stashed_nodes)
        hash = util.INLINE_PLACEHOLDER % id
        return hash, id

    def __findPlaceholder(self, data, index):
        """Extract id from data string, start from index.

        Args:
            data (str): text
            index (int): index from which we start search

        Returns:
            (str, int): placeholder id and index after the found placeholder.
        """
        m = self.__placeholder_re.search(data, index)
        if m:
            return m.group(1), m.end()
        else:
            return None, index + 1

    def __stashNode(self, node, type):
        """Add node to stash."""
        placeholder, id = self.__makePlaceholder(type)
        self.stashed_nodes[id] = node
        return placeholder

    def __handleInline(self, data, patternIndex=0):
        """Replace placeholders of texts with inline patterns.

        Args:
            data (str): A line of Markdown text
            patternIndex (int): The index of the inlinePattern to start with

        Returns:
            (str): Text with placeholders.
        """
        if not isinstance(data, util.AtomicString):
            startIndex = 0
            while patternIndex < len(self.inlinePatterns):
                data, matched, startIndex = self.__applyPattern(
                    self.inlinePatterns.value_for_index(patternIndex),
                    data, patternIndex, startIndex)
                if not matched:
                    patternIndex += 1
        return data

    def __processElementText(self, node, subnode, isText=True):
        """Process text placeholders of stashed nodes.

        Args:
            node (Element): parent node
            subnode (Element): processing node
            isText (bool): True - it's text, False - it's tail
        """
        if isText:
            text = subnode.text
            subnode.text = None
        else:
            text = subnode.tail
            subnode.tail = None

        childResult = self.__processPlaceholders(text, subnode, isText)

        if not isText and node is not subnode:
            pos = list(node).index(subnode) + 1
        else:
            pos = 0

        childResult.reverse()
        for newChild in childResult:
            node.insert(pos, newChild)

    def __processPlaceholders(self, data, parent, isText=True):
        """Process string with placeholders and generate ElementTree tree.

        Args:
            data (str): text with placeholders instead of ElementTree elements.
            parent (Element): Element which contains processing inline data
            isText (bool): True - it's text, False - it's tail

        Returns:
            (list[ElementTree]): elements with applied inline patterns.
        """
        def linkText(text):
            if text:
                if result:
                    if result[-1].tail:
                        result[-1].tail += text
                    else:
                        result[-1].tail = text
                elif not isText:
                    if parent.tail:
                        parent.tail += text
                    else:
                        parent.tail = text
                else:
                    if parent.text:
                        parent.text += text
                    else:
                        parent.text = text
        result = []
        strartIndex = 0
        while data:
            index = data.find(self.__placeholder_prefix, strartIndex)
            if index != -1:
                id, phEndIndex = self.__findPlaceholder(data, index)

                if id in self.stashed_nodes:
                    node = self.stashed_nodes.get(id)

                    if index > 0:
                        text = data[strartIndex:index]
                        linkText(text)

                    if not isString(node):  # it's Element
                        for child in [node] + list(node):
                            if child.tail:
                                if child.tail.strip():
                                    self.__processElementText(
                                        node, child, False
                                    )
                            if child.text:
                                if child.text.strip():
                                    self.__processElementText(child, child)
                    else:  # it's just a string
                        linkText(node)
                        strartIndex = phEndIndex
                        continue

                    strartIndex = phEndIndex
                    result.append(node)

                else:  # wrong placeholder
                    end = index + len(self.__placeholder_prefix)
                    linkText(data[strartIndex:end])
                    strartIndex = end
            else:
                text = data[strartIndex:]
                if isinstance(data, util.AtomicString):
                    # We don't want to loose the AtomicString
                    text = util.AtomicString(text)
                linkText(text)
                data = ""

        return result

    def __applyPattern(self, pattern, data, patternIndex, startIndex=0):
        """Add the pattern to stashed_nodes if the line fits the pattern.

        Check if the line fits the pattern, create the necessary
        elements, add it to stashed_nodes.

        Args:
            data (str): the text to be processed
            pattern (str): the pattern to be checked
            patternIndex (int): index of current pattern
            startIndex (int): string index, from which we start searching

        Returns:
            (str): text with placeholders instead of ElementTree elements.
        """
        match = pattern.getCompiledRegExp().match(data[startIndex:])
        leftData = data[:startIndex]

        if not match:
            return data, False, 0

        node = pattern.handleMatch(match)

        if node is None:
            return data, True, len(leftData)+match.span(len(match.groups()))[0]

        if not isString(node):
            if not isinstance(node.text, util.AtomicString):
                # We need to process current node too
                for child in [node] + list(node):
                    if not isString(node):
                        if child.text:
                            child.text = self.__handleInline(
                                child.text, patternIndex + 1
                            )
                        if child.tail:
                            child.tail = self.__handleInline(
                                child.tail, patternIndex
                            )

        placeholder = self.__stashNode(node, pattern.type())

        return "%s%s%s%s" % (leftData,
                             match.group(1),
                             placeholder, match.groups()[-1]), True, 0

    def run(self, tree):
        """Apply inline patterns to a parsed Markdown tree.

        Iterate over ElementTree, find elements with inline tag, apply inline
        patterns and append newly created Elements to tree.  If you don't
        want to process your data with inline paterns, instead of normal
        string, use subclass AtomicString:

            node.text = markdown.AtomicString("This will not be processed.")

        Args:
            tree (ElementTree): Markdown tree.

        Returns:
            (ElementTree): Tree with applied inline patterns.
        """
        self.stashed_nodes = {}

        stack = [tree]

        while stack:
            currElement = stack.pop()
            insertQueue = []
            for child in currElement:
                if child.text and not isinstance(
                    child.text, util.AtomicString
                ):
                    text = child.text
                    child.text = None
                    lst = self.__processPlaceholders(
                        self.__handleInline(text), child
                    )
                    stack += lst
                    insertQueue.append((child, lst))
                if child.tail:
                    tail = self.__handleInline(child.tail)
                    dumby = util.etree.Element('d')
                    child.tail = None
                    tailResult = self.__processPlaceholders(tail, dumby, False)
                    if dumby.tail:
                        child.tail = dumby.tail
                    pos = list(currElement).index(child) + 1
                    tailResult.reverse()
                    for newChild in tailResult:
                        currElement.insert(pos, newChild)
                if len(child):
                    stack.append(child)

            for element, lst in insertQueue:
                if self.markdown.enable_attributes:
                    if element.text and isString(element.text):
                        element.text = inlinepatterns.handleAttributes(
                            element.text, element
                        )
                i = 0
                for newChild in lst:
                    if self.markdown.enable_attributes:
                        # Processing attributes
                        if newChild.tail and isString(newChild.tail):
                            newChild.tail = inlinepatterns.handleAttributes(
                                newChild.tail, element
                            )
                        if newChild.text and isString(newChild.text):
                            newChild.text = inlinepatterns.handleAttributes(
                                newChild.text, newChild
                            )
                    element.insert(i, newChild)
                    i += 1
        return tree


class PrettifyTreeprocessor(Treeprocessor):
    """Add linebreaks to the html document."""

    def _prettifyETree(self, elem):
        """Recursively add linebreaks to ElementTree children."""
        i = "\n"
        if util.isBlockLevel(elem.tag) and elem.tag not in ['code', 'pre']:
            if (not elem.text or not elem.text.strip()) \
                    and len(elem) and util.isBlockLevel(elem[0].tag):
                elem.text = i
            for e in elem:
                if util.isBlockLevel(e.tag):
                    self._prettifyETree(e)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        if not elem.tail or not elem.tail.strip():
            elem.tail = i

    def run(self, root):
        """Add linebreaks to ElementTree root object."""
        self._prettifyETree(root)
        # Do <br />'s seperately as they are often in the middle of
        # inline content and missed by _prettifyETree.
        brs = root.iter('br')
        for br in brs:
            if not br.tail or not br.tail.strip():
                br.tail = '\n'
            else:
                br.tail = '\n%s' % br.tail
        # Clean up extra empty lines at end of code blocks.
        pres = root.iter('pre')
        for pre in pres:
            if len(pre) and pre[0].tag == 'code':
                pre[0].text = util.AtomicString(pre[0].text.rstrip() + '\n')
