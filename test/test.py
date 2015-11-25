#!/usr/bin/python

import SocketServer
import jsonrpc
import apiTest

class Handler(SocketServer.BaseRequestHandler):
    """JSON-RPC-server.

    Accepts calls for the registered classes (hardcoded for now).

    :TODO:
        - logging/loglevels?
    """

    # set apiModel
    test  = apiTest.apiTest()

    def setup(self):
        SocketServer.BaseRequestHandler.setup(self)

        self.__data_serializer = jsonrpc.JsonRpc10()

        self.funcs = {}
        self.register_instance(self.test, name = "test")


    def logfile(self, message):
        print(message)

    def register_instance(self, myinst, name = None):
        """Add all functions of a class-instance to the RPC-services.

        All entries of the instance which do not begin with '_' are added.

        :Parameters:
            - myinst: class-instance containing the functions
            - name:   | hierarchical prefix.
                      | If omitted, the functions are added directly.
                      | If given, the functions are added as "name.function".
        :TODO:
            - only add functions and omit attributes?
            - improve hierarchy?
        """
        for e in dir(myinst):
            if e[0][0] != "_":
                if name is None:
                    self.register_function(getattr(myinst, e))
                else:
                    self.register_function(getattr(myinst, e), name="%s.%s" % (name, e))

    def register_function(self, function, name = None):
        """Add a function to the RPC-services.

        :Parameters:
            - function: function to add
            - name:     RPC-name for the function. If omitted/None, the original
                        name of the function is used.
        """
        if name is None:
            self.funcs[function.__name__] = function
        else:
            self.funcs[name] = function


    def dispatch(self, rpcstr):
        """Handle a RPC-Request.

        :Parameters:
            - rpcstr: the received rpc-string
        :Returns: the data to send back or None if nothing should be sent back
        :Raises:  RPCFault (and maybe others)
        """
        notification = False
        try:
            req = self.__data_serializer.loads_request(rpcstr)
            if len(req) == 2:       #notification
                method, params = req
                notification = True
            else:                   #request
                method, params, id = req

        except RPCFault, err:
            return self.__data_serializer.dumps_error(err, id = None)

        except Exception, err:
            self.logfile("%d (%s): %s" % (INTERNAL_ERROR, ERROR_MESSAGE[INTERNAL_ERROR], str(err)))
            exc_type, exc_value, exc_traceback = sys.exc_info();
            self.logfile(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            return self.__data_serializer.dumps_error( RPCFault(INTERNAL_ERROR, ERROR_MESSAGE[INTERNAL_ERROR]), id = None)

        if method not in self.funcs:
            if notification:
                return None
            return self.__data_serializer.dumps_error( RPCFault(METHOD_NOT_FOUND, ERROR_MESSAGE[METHOD_NOT_FOUND]), id )

        try:
            if isinstance(params, dict):
                result = self.funcs[method](**params)
            else:
                result = self.funcs[method](*params)

        except RPCFault, err:
            if notification:
                return None
            return self.__data_serializer.dumps_error(err, id = None)

        except Exception, err:
            if notification:
                return None
            self.logfile("%d (%s): %s" % (INTERNAL_ERROR, ERROR_MESSAGE[INTERNAL_ERROR], str(err)))
            exc_type, exc_value, exc_traceback = sys.exc_info();
            self.logfile(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            return self.__data_serializer.dumps_error(RPCFault(INTERNAL_ERROR, ERROR_MESSAGE[INTERNAL_ERROR]), id)

        if notification:
            return None

        try:
            return self.__data_serializer.dumps_response(result, id)

        except Exception, err:
            self.logfile("%d (%s): %s" % (INTERNAL_ERROR, ERROR_MESSAGE[INTERNAL_ERROR], str(err)))
            exc_type, exc_value, exc_traceback = sys.exc_info();
            self.logfile(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            return self.__data_serializer.dumps_error(RPCFault(INTERNAL_ERROR, ERROR_MESSAGE[INTERNAL_ERROR]), id)


    def handle(self):
        """
        Handle data transfer and dispatching
        """
        data = self.request.recv(4096).strip()
        self.logfile("Request: " + data)
        reply = self.dispatch(data)
        self.logfile("Reply: " + reply)
        self.request.sendall(reply)

if __name__ == "__main__":
    # Welcome message
    print "Starting test server.."

    # select one of these to create the server of your desires / nightmares
    server = SocketServer.TCPServer(("127.0.0.1", 3000), Handler)
    #server = SocketServer.ForkingTCPServer(("127.0.0.1", 3000), Handler)
    #server = SocketServer.ThreadingTCPServer(("apiSettings.apiListenAddr127.0.0.1", 3000), Handler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print "Interrupt received, quiting test server.."
        server.shutdown()
        exit()
