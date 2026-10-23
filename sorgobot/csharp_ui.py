"""Native editor for the supported Linux C# scripting interface."""
import copy
import re
import uuid
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QPlainTextEdit,QComboBox,QCheckBox,QSpinBox,QPushButton,QDialogButtonBox,QTabWidget,QWidget,QTableWidget,QTableWidgetItem,QFileDialog
from .core import walk
from .csharp_editor import CSharpEditor


class CSharpDialog(QDialog):
    def __init__(self,value,host):
        super().__init__(host);self.host=host;self.value=copy.deepcopy(value);self.kind=value['type']
        self.setWindowTitle('Execute C# Code' if self.kind==90060 else 'Execute C# Method');self.resize(800,690)
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.selected_refs=list(value.get('references',[]));self.request_id=None;self.save_after_compile=False
        self.code_nodes=[n for a in host.store.read('actions.json')['actions'] for n in walk(a.get('subActions',[])) if n.get('type')==90060 and n.get('name')]
        if self.kind==90060:
            self.name=QLineEdit(value.get('name',''));form.addRow('Name',self.name)
            self.description=QLineEdit(value.get('description',''));form.addRow('Description',self.description)
        else:
            self.reference=QComboBox()
            for node in self.code_nodes:self.reference.addItem(node['name']+' ('+node['id'][:8]+')',node['id'])
            selected=value.get('codeId','');index=self.reference.findData(selected)
            if index<0 and selected:self.reference.addItem('Missing: '+selected,selected);index=self.reference.count()-1
            self.reference.setCurrentIndex(max(0,index));form.addRow('Execute C# Code',self.reference)
            self.method=QComboBox();form.addRow('Method',self.method)
            self.reference.currentIndexChanged.connect(self.methods);self.methods(initial=True)
        self.save=QCheckBox('Save Result to Variable');self.save.setChecked(value.get('saveResult',False));form.addRow('',self.save)
        self.variable=QLineEdit(value.get('resultVariable','csharpResult'));form.addRow('Variable Name',self.variable)
        self.timeout=QSpinBox();self.timeout.setRange(1,600);self.timeout.setValue(int(value.get('timeout',30)));self.timeout.setSuffix(' s');form.addRow('Timeout',self.timeout)
        self.save.toggled.connect(self.variable.setEnabled);self.variable.setEnabled(self.save.isChecked())
        hint=QLabel('Linux .NET · CPHInline mit öffentlichen bool-Methoden ohne Parameter. Unterstützt: args, TryGetArg, SetArgument, Globals/User-Variablen, Actions/Queues und Log. Init/Dispose und Klassenfelder werden je Codeinstanz verwaltet. Vorschau simuliert Bot-Ausgaben; eigener C#-Datei-/Netzwerkcode wird ausgeführt.');hint.setWordWrap(True);layout.addWidget(hint)
        if self.kind==90060:
            self.code=CSharpEditor(value.get('code',''));self.code.setFont(QFont('monospace',11));self.code.setTabStopDistance(self.code.fontMetrics().horizontalAdvance(' ')*4);layout.addWidget(self.code,1)
        else:layout.addStretch()
        self.tabs=QTabWidget();layout.addWidget(self.tabs)
        self.output=QPlainTextEdit();self.output.setReadOnly(True);self.output.setMaximumHeight(150);self.tabs.addTab(self.output,'Compiling Log')
        refs_page=QWidget();refs_layout=QVBoxLayout(refs_page)
        self.refs_table=QTableWidget(0,3);self.refs_table.setHorizontalHeaderLabels(['Reference','Source','Path']);self.refs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);refs_layout.addWidget(self.refs_table)
        refs_buttons=QHBoxLayout();refs_layout.addLayout(refs_buttons)
        add=QPushButton('Add DLL');add.clicked.connect(self.add_reference);refs_buttons.addWidget(add)
        remove=QPushButton('Remove');remove.clicked.connect(self.remove_reference);refs_buttons.addWidget(remove);refs_buttons.addStretch()
        add.setEnabled(self.kind==90060);remove.setEnabled(self.kind==90060)
        self.tabs.addTab(refs_page,'References');self.show_references()

        settings_page=QWidget();settings_form=QFormLayout(settings_page)
        self.precompile=QCheckBox('Precompile on Application Start');self.precompile.setChecked(value.get('precompile',False));settings_form.addRow(self.precompile)
        self.delayed=QCheckBox('Delayed Start');self.delayed.setChecked(value.get('delayedStart',False));self.delayed.setEnabled(self.precompile.isChecked());self.precompile.toggled.connect(self.delayed.setEnabled);settings_form.addRow(self.delayed)
        self.precompile.setEnabled(self.kind==90060);self.delayed.setEnabled(self.kind==90060 and self.precompile.isChecked())
        self.tabs.addTab(settings_page,'Settings')
        editor_page=QWidget();editor_form=QFormLayout(editor_page)
        try:self.preferences=host.store.read('editor.json')
        except FileNotFoundError:self.preferences={}
        pref=self.preferences.get('csharp',{})
        self.font_size=QSpinBox();self.font_size.setRange(8,32);self.font_size.setValue(pref.get('fontSize',11));editor_form.addRow('Font Size',self.font_size)
        self.indentation=QComboBox()
        for size in (2,4,8):self.indentation.addItem(str(size),size)
        self.indentation.setCurrentIndex(max(0,self.indentation.findData(pref.get('indent',4))));editor_form.addRow('Indentation',self.indentation)
        self.word_wrap=QCheckBox('Word Wrap');self.word_wrap.setChecked(pref.get('wrap',False));editor_form.addRow(self.word_wrap)
        self.line_numbers=QCheckBox('Line Numbers');self.line_numbers.setChecked(pref.get('lineNumbers',True));editor_form.addRow(self.line_numbers)
        self.syntax=QCheckBox('Syntax Highlighting');self.syntax.setChecked(pref.get('highlight',True));editor_form.addRow(self.syntax)
        self.tabs.addTab(editor_page,'Editor Settings');editor_page.setEnabled(self.kind==90060)
        for widget in (self.font_size,self.indentation):
            (widget.valueChanged if isinstance(widget,QSpinBox) else widget.currentIndexChanged).connect(self.apply_editor_settings)
        for widget in (self.word_wrap,self.line_numbers,self.syntax):widget.toggled.connect(self.apply_editor_settings)
        self.apply_editor_settings()
        row=QHBoxLayout();layout.addLayout(row);
        self.format=QPushButton('Format Document');self.format.clicked.connect(self.format_document);self.format.setEnabled(self.kind==90060);row.addWidget(self.format)
        self.compile=QPushButton('Compile');self.compile.clicked.connect(self.compile_code);row.addWidget(self.compile)
        self.find_refs=QPushButton('Find Refs');self.find_refs.clicked.connect(self.find_references);self.find_refs.setEnabled(self.kind==90060);row.addWidget(self.find_refs);row.addStretch()
        self.save_compile=QPushButton('Save and Compile');self.save_compile.clicked.connect(self.save_and_compile);row.addWidget(self.save_compile)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);row.addWidget(buttons)
        self.runtime=getattr(host,'runtime',None)
        if self.runtime:
            self.runtime.result.connect(self.compiled);self.finished.connect(self.disconnect_runtime)
        else:self.set_busy(True)
    def selected_code(self):
        if self.kind==90060:return self.code.toPlainText()
        return next((n.get('code','') for n in self.code_nodes if n['id']==self.reference.currentData()),'')
    def methods(self,*_,initial=False):
        selected=self.value.get('method','Execute') if initial else 'Execute';self.method.clear()
        code=next((n.get('code','') for n in self.code_nodes if n['id']==self.reference.currentData()),'')
        for name in dict.fromkeys(re.findall(r'public\s+bool\s+(\w+)\s*\(\s*\)',code)):self.method.addItem(name,name)
        index=self.method.findData(selected)
        if index<0 and initial and selected:self.method.addItem('Missing: '+selected,selected);index=self.method.count()-1
        self.method.setCurrentIndex(max(0,index))
        if hasattr(self,'refs_table'):self.show_references()
    def apply_editor_settings(self,*_):
        if self.kind==90060:self.code.apply_settings(self.font_size.value(),self.indentation.currentData(),self.word_wrap.isChecked(),self.line_numbers.isChecked(),self.syntax.isChecked())
    def set_busy(self,busy):
        self.compile.setEnabled(not busy);self.save_compile.setEnabled(not busy)
        self.find_refs.setEnabled(not busy and self.kind==90060);self.format.setEnabled(not busy and self.kind==90060)
    def format_document(self):
        self.set_busy(True);self.save_after_compile=False
        self.request_id=uuid.uuid4().hex;self.request_code=self.selected_code();self.request_refs=list(self.references_for_compile())
        self.runtime.submit('csharp_format',code=self.request_code,indent=self.indentation.currentData(),requestId=self.request_id)
    def save_and_compile(self):
        if not self.valid_input():return
        self.save_after_compile=True;self.compile_code()
    def compile_code(self):
        self.set_busy(True);self.output.setPlainText('Compiling…')
        self.request_id=uuid.uuid4().hex;self.request_code=self.selected_code();self.request_refs=list(self.references_for_compile())
        self.runtime.submit('csharp_compile',code=self.selected_code(),references=self.references_for_compile(),codeId=self.value.get('id') if self.kind==90060 else self.reference.currentData(),timeout=self.timeout.value(),requestId=self.request_id)
    def references_for_compile(self):
        if self.kind==90060:return self.selected_refs
        return next((n.get('references',[]) for n in self.code_nodes if n['id']==self.reference.currentData()),[])
    def show_references(self,detected=None):
        from pathlib import Path
        entries=detected or [{'name':Path(p).name,'path':p,'kind':'Local DLL'} for p in self.references_for_compile()]
        listed={e['path'] for e in entries}
        entries=[*entries,*[{'name':Path(p).name,'path':p,'kind':'Local DLL'} for p in self.references_for_compile() if p not in listed]]
        self.refs_table.setRowCount(0)
        for entry in entries:
            row=self.refs_table.rowCount();self.refs_table.insertRow(row)
            for col,key in enumerate(('name','kind','path')):self.refs_table.setItem(row,col,QTableWidgetItem(entry[key]))
        self.refs_table.resizeColumnsToContents()
    def add_reference(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Add References','','Managed assemblies (*.dll)')
        self.selected_refs=list(dict.fromkeys([*self.selected_refs,*paths]));self.show_references()
    def remove_reference(self):
        row=self.refs_table.currentRow()
        if row<0:return
        path=self.refs_table.item(row,2).text()
        self.selected_refs=[p for p in self.selected_refs if p!=path];self.show_references()
    def find_references(self):
        self.set_busy(True);self.save_after_compile=False;self.output.setPlainText('Finding references…')
        self.request_id=uuid.uuid4().hex;self.request_code=self.selected_code();self.request_refs=list(self.references_for_compile())
        self.runtime.submit('csharp_find_refs',code=self.selected_code(),references=self.selected_refs,requestId=self.request_id)
    def compiled(self,kind,result):
        if kind not in ('csharp_compile','csharp_find_refs','csharp_format') or result.get('requestId')!=self.request_id:return
        self.set_busy(False)
        if getattr(self,'request_code',self.selected_code())!=self.selected_code() or getattr(self,'request_refs',self.references_for_compile())!=self.references_for_compile():
            self.save_after_compile=False;self.output.setPlainText('Code or references changed during analysis. Please run Compile or Find Refs again.');return
        if kind=='csharp_format':
            if result.get('success'):
                cursor=self.code.textCursor();cursor.select(cursor.SelectionType.Document);cursor.insertText(result['code']);self.output.setPlainText('Document formatted.')
            else:self.output.setPlainText(result.get('message','Format failed.'))
            return
        if kind=='csharp_find_refs':
            if 'selected' in result:
                self.selected_refs=result['selected'];self.show_references(result.get('references',[]));self.tabs.setCurrentIndex(1)
            diagnostics=result.get('diagnostics',[])
            self.output.setPlainText(result.get('message') or ('References found: '+str(len(result.get('references',[])))+'\n'+'\n'.join(diagnostics)))
        else:
            self.output.setPlainText(result.get('message',''));self.tabs.setCurrentIndex(0)
            if self.save_after_compile and result.get('success'):self.accept()
            self.save_after_compile=False
    def disconnect_runtime(self,*_):
        try:self.runtime.result.disconnect(self.compiled)
        except (RuntimeError,TypeError):pass
    def valid_input(self):
        if self.save.isChecked() and not self.variable.text().strip():self.output.setPlainText('Variable Name is required.');return False
        if self.kind==90060 and not self.code.toPlainText().strip():self.output.setPlainText('Code is required.');return False
        if self.kind==90061 and (not self.reference.currentData() or not self.method.currentData()):self.output.setPlainText('Code and Method are required.');return False
        return True
    def accept(self):
        if not self.valid_input():return
        self.value.update(saveResult=self.save.isChecked(),resultVariable=self.variable.text().strip(),timeout=self.timeout.value())
        if self.kind==90060:
            self.value.update(name=self.name.text().strip(),description=self.description.text(),code=self.code.toPlainText(),references=list(self.selected_refs),precompile=self.precompile.isChecked(),delayedStart=self.delayed.isChecked())
            # Read the latest preferences so other editor settings are preserved.
            try:preferences=self.host.store.read('editor.json')
            except FileNotFoundError:preferences={}
            preferences['csharp']={'fontSize':self.font_size.value(),'indent':self.indentation.currentData(),'wrap':self.word_wrap.isChecked(),'lineNumbers':self.line_numbers.isChecked(),'highlight':self.syntax.isChecked()}
            self.host.store.save('editor.json',preferences)
        else:self.value.update(codeId=self.reference.currentData(),method=self.method.currentData())
        super().accept()
