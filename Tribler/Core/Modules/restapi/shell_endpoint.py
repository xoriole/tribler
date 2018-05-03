import code
import io
import json
import sys
from twisted.web import http, resource

from Tribler.Core.version import version_id


class Stream(object):
    def __init__(self):
        self.stream = io.BytesIO()

    def read(self, *args, **kwargs):
        result = self.stream.read(*args, **kwargs)
        self.stream = io.BytesIO(self.stream.read())

        return result

    def write(self, *args, **kwargs):
        p = self.stream.tell()
        self.stream.seek(0, io.SEEK_END)
        result = self.stream.write(*args, **kwargs)
        self.stream.seek(p)

        return result


class Console(object):
    def __init__(self, locals=None):
        self.console = code.InteractiveConsole(locals=locals)

        self.stdout = Stream()
        self.stderr = Stream()

    def runcode(self, *args, **kwargs):
        stdout = sys.stdout
        sys.stdout = self.stdout

        stderr = sys.stderr
        sys.stderr = self.stderr

        result = None
        try:
            result = self.console.runcode(*args, **kwargs)
        except SyntaxError:
            self.console.showsyntaxerror()
        except:
            self.console.showtraceback()

        sys.stdout = stdout

        sys.stderr = stderr

        return result

    def execute(self, command):
        return self.runcode(code.compile_command(command))


class ShellEndpoint(resource.Resource):
    """
    This class provides the execution environment for Tribler Shell.
    """

    def __init__(self, session):
        resource.Resource.__init__(self)
        self.session = session

        variables = globals().copy()
        variables.update(locals())
        variables['session'] = self.session
        self.shell = Console(locals=variables)

    def render_GET(self, request):
        return json.dumps({"version": version_id})

    def render_POST(self, request):
        parameters = http.parse_qs(request.content.read(), 1)
        if 'code' not in parameters or len(parameters['code']) == 0:
            request.setResponseCode(http.BAD_REQUEST)
            return json.dumps({"error": "code parameter missing"})

        # Execute the code
        output = self.shell.runcode(parameters['code'][0].decode('utf-8'))
        stdout = self.shell.stdout.read()
        stderr = self.shell.stderr.read()

        output = str(output).decode('unicode_escape').encode('utf-8').strip() if output else None
        stdout = stdout.decode('unicode_escape').encode('utf-8').strip() if stdout else None
        stderr = stderr.decode('unicode_escape').encode('utf-8').strip() if stderr else None

        return json.dumps({"output": output, "stdout": stdout, "stderr": stderr})