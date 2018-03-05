import re
import os

class CodeBuilder:
    INDENT_STEP = 4

    def __init__(self, indent=0):
        self.indent = indent
        self.lines = []

    def forward(self):
        self.indent += self.INDENT_STEP

    def backward(self):
        self.indent -= self.INDENT_STEP

    def add(self, code):
        self.lines.append(code)

    def add_line(self, code):
        self.lines.append(' ' * self.indent + code)

    def __str__(self):
        return '\n'.join(map(str, self.lines))

    def __repr__(self):
        return str(self)



class Template:

    def __init__(self, raw_text, indent=0, default_context=None,
                 func_name='__func_name', result_var='__result',
                 template_dir='', encoding='utf-8'):
        self.raw_text = raw_text
        self.default_context = default_context or {}
        self.func_name = func_name
        self.result_var = result_var
        self.template_dir = template_dir
        self.encoding = encoding
        self.code_builder = code_builder = CodeBuilder(indent=indent)
        self.buffered = []
        self.re_variable = re.compile(r'\{\{.*?\}\}')
        self.re_tag = re.compile(r'\{% .*? %\}')
        self.re_tokens = re.compile(r'''(
            (?:\{\{ .*? \}\})
            |(?:\{% .*? %\})
        )''', re.X)

        code_builder.add_line('def {}():'.format(self.func_name))
        code_builder.forward()

        code_builder.add_line('{} = []'.format(self.result_var))
        self._parse_text()

        self.flush_buffer()

        code_builder.add_line('return "".join({})'.format(self.result_var))
        code_builder.backward()

    def _parse_text(self):
        tokens = self.re_tokens.split(self.raw_text)
        handlers = (
            (self.re_variable.match, self._handle_variable),
            (self.re_tag.match, self._handle_tag),
        )
        default_handler = self._handle_string

        for token in tokens:
            for match, handler in handlers:
                if match(token):
                    handler(token)
                    break
            else:
                default_handler(token)

        for token in tokens:
            if self.re_variable.match(token):
                variable = token.strip('{} ')
                self.buffered.append('str({})'.format(variable))
            elif self.re_tag.match(token):
                self.flush_buffer()
                tag = token.strip('{%} ')
                tag_name = tag.split()[0]
                if tag_name in ('if', 'elif', 'else', 'for'):
                    if tag_name in ('elif', 'else'):
                        self.code_builder.backward()
                    self.code_builder.add_line('{}:'.format(tag))
                    self.code_builder.forward()
                elif tag_name in ('break'):
                    self.code_builder.add_line(tag)
                elif tag_name in ('endif', 'endfor'):
                    self.code_builder.backward()
            else:
                self.buffered.append(repr(token))

    def _handle_string(self, token):
        self.buffered.append(repr(token))

    def _handle_variable(self, token):
        variable = token.strip('{} ')
        self.buffered.append('str({})'.format(variable))

    def _handle_tag(self, token):
        self.flush_buffer()
        tag = token.strip('{%} ')
        tag_name = tag.split()[0]
        if tag_name == 'include':
            self._handle_include(tag)
        else:
            self._handle_statement(tag, tag_name)

    def _handle_include(self, tag):
        filename = tag.split()[1].strip('"\'')
        include_template = self._parse_another_template_file(filename)
        self.code_builder.add(include_template.code_builder)
        self.code_builder.add_line(
            '{0}.append({1}())'.format(
                self.result_var, include_template.func_name
            )
        )

    def _handle_statement(self, tag, tag_name):
        if tag_name in ('if', 'elif', 'else', 'for'):
            if tag_name in ('elif', 'else'):
                self.code_builder.backward()
            self.code_builder.add_line('{}:'.format(tag))
            self.code_builder.forward()
        elif tag_name in ('break'):
            self.code_builder.add_line(tag)
        elif tag_name in ('endif', 'endfor'):
            self.code_builder.backward()

    def _parse_another_template_file(self, filename):
        template_path = os.path.realpath(
            os.path.join(self.template_dir, filename)
        )
        name_suffix = str(hash(template_path)).replace('-', '_')
        func_name = '{}_{}'.format(self.func_name, name_suffix)
        result_var = '{}_{}'.format(self.result_var, name_suffix)

        with open(template_path, encoding=self.encoding) as f:
            template = self.__class__(
                f.read(), indent=self.code_builder.indent,
                default_context=self.default_context,
                func_name=func_name, result_var=result_var,
                template_dir=self.template_dir
            )
        return template

    def flush_buffer(self):
        line = '{0}.extend([{1}])'.format(
            self.result_var,
            ','.join(self.buffered)
        )

        self.code_builder.add_line(line)
        self.buffered = []

    def render(self, context=None):
        namespace = {}
        namespace.update(self.default_context)
        if context:
            namespace.update(context)
        exec(str(self.code_builder), namespace)
        result = namespace[self.func_name]()
        return result
