"""Native C# editor with line numbers and token-based syntax highlighting."""
from PySide6.QtCore import Qt,QRect,QSize
from PySide6.QtGui import QColor,QPainter,QSyntaxHighlighter,QTextCharFormat,QFont,QTextCursor
from PySide6.QtWidgets import QPlainTextEdit,QWidget

class LineNumbers(QWidget):
    def __init__(self,editor):super().__init__(editor);self.editor=editor
    def sizeHint(self):return QSize(self.editor.number_width(),0)
    def paintEvent(self,event):self.editor.paint_numbers(event)

class CSharpHighlight(QSyntaxHighlighter):
    def __init__(self,document):
        super().__init__(document)
        import re
        self.pattern=re.compile(r'//[^\n]*|/\*|\*/|@"(?:""|[^"])*"|"(?:\\.|[^"\\])*"|\b(?:using|public|private|protected|class|static|bool|string|int|double|var|void|return|if|else|while|for|foreach|break|continue|new|true|false|null|async|await|try|catch|throw|namespace|out|in|ref|this)\b|\b\d+(?:\.\d+)?\b')
        self.styles={}
        for name,color in [('comment','#77ac75'),('string','#d9ab82'),('keyword','#70b9ed'),('number','#c2d7a0')]:
            fmt=QTextCharFormat();fmt.setForeground(QColor(color));self.styles[name]=fmt
    def highlightBlock(self,text):
        self.setCurrentBlockState(0);start=0
        if self.previousBlockState()==1:
            end=text.find('*/');length=len(text) if end<0 else end+2
            self.setFormat(0,length,self.styles['comment'])
            if end<0:self.setCurrentBlockState(1);return
            start=length
        for match in self.pattern.finditer(text,start):
            token=match.group()
            if token=='/*':
                end=text.find('*/',match.end());length=len(text)-match.start() if end<0 else end+2-match.start()
                self.setFormat(match.start(),length,self.styles['comment'])
                if end<0:self.setCurrentBlockState(1)
                # Process the suffix with the same lexer; prevent strings in comments changing state.
                if end>=0:
                    for suffix in self.pattern.finditer(text,end+2):self.color_token(suffix)
                return
            self.color_token(match)
    def color_token(self,match):
        token=match.group();kind='comment' if token.startswith('//') else 'string' if token.startswith(('"','@"')) else 'number' if token[0].isdigit() else 'keyword'
        # Qt uses UTF-16 indices, including supplementary Unicode in strings/comments.
        text=match.string;start=len(text[:match.start()].encode('utf-16-le'))//2;length=len(token.encode('utf-16-le'))//2
        self.setFormat(start,length,self.styles[kind])

class CSharpEditor(QPlainTextEdit):
    def __init__(self,text):
        super().__init__(text);self.numbers=LineNumbers(self);self.highlight=CSharpHighlight(self.document());self.indent=4;self.show_numbers=True
        self.blockCountChanged.connect(self.update_margin);self.updateRequest.connect(self.update_numbers);self.update_margin()
    def number_width(self):return 12+self.fontMetrics().horizontalAdvance('9')*len(str(max(1,self.blockCount()))) if self.show_numbers else 0
    def update_margin(self,*_):self.setViewportMargins(self.number_width(),0,0,0);self.numbers.setVisible(self.show_numbers)
    def update_numbers(self,rect,dy):
        if dy:self.numbers.scroll(0,dy)
        else:self.numbers.update(0,rect.y(),self.numbers.width(),rect.height())
        if rect.contains(self.viewport().rect()):self.update_margin()
    def resizeEvent(self,event):
        super().resizeEvent(event);rect=self.contentsRect();self.numbers.setGeometry(QRect(rect.left(),rect.top(),self.number_width(),rect.height()))
    def paint_numbers(self,event):
        painter=QPainter(self.numbers);painter.fillRect(event.rect(),QColor('#202428'));painter.setPen(QColor('#a4a9af'));painter.setFont(self.font())
        block=self.firstVisibleBlock();top=int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top<=event.rect().bottom():
            height=int(self.blockBoundingRect(block).height())
            if block.isVisible() and top+height>=event.rect().top():painter.drawText(0,top,self.numbers.width()-6,self.fontMetrics().height(),Qt.AlignmentFlag.AlignRight,str(block.blockNumber()+1))
            top+=height;block=block.next()
    def apply_settings(self,size,indent,wrap,numbers,highlight):
        self.setFont(QFont('monospace',size));self.indent=indent;self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ')*indent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if wrap else QPlainTextEdit.LineWrapMode.NoWrap)
        self.show_numbers=numbers;self.update_margin();self.resizeEvent_dummy()
        self.highlight.setDocument(self.document() if highlight else None)
    def resizeEvent_dummy(self):
        rect=self.contentsRect();self.numbers.setGeometry(rect.left(),rect.top(),self.number_width(),rect.height())
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Tab and not event.modifiers() and not self.textCursor().hasSelection():self.insertPlainText(' '*self.indent);return
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and not event.modifiers():
            cursor=self.textCursor();before=cursor.block().text()[:cursor.positionInBlock()]
            indentation=before[:len(before)-len(before.lstrip())]
            if before.rstrip().endswith('{'):indentation+=' '*self.indent
            super().keyPressEvent(event);self.insertPlainText(indentation);return
        super().keyPressEvent(event)
