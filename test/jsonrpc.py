#!/usr/bin/python

"""
JSON-RPC (remote procedure call) server.

Consists of two parts:
    - dispatcher
    - data structure / serializer


Currently JSON-RPC 1.0 is implemented

:Version:   20141118
:Status:    experimental


:Note:      all exceptions derived from RPCFault are propagated to the client.
            other exceptions are logged and result in a sent-back "empty" INTERNAL_ERROR.
:Uses:      simplejson, time, codecs
:SeeAlso:   JSON-RPC 1.0 specification
:Warning:
    .. Warning::
        This is **experimental** code!

:Author:    Leo Noordergraaf leo.noordergraaf@deanconnect.nl
:Copyright: 2014 by Dean Connect
:Author:    Roland Koebler (rk(at)simple-is-better.org)
:Copyright: 2007-2008 by Roland Koebler (rk(at)simple-is-better.org)
:License:   see __license__
:Changelog:
        - 2014-11-18:     1st release

TODO:
        - transport: SSL sockets, maybe HTTP, HTTPS
        - types: support for date/time (ISO 8601)
        - errors: maybe customizable error-codes/exceptions
        - maybe test other json-serializers, like cjson?
"""

__version__ = "2014-11-18"
__author__   = "Leo Noordergraaf <leo.noordergraaf@deanconnect.nl>"
__license__  = """Copyright (c) 2014 by Leo Noordergraaf (leo.noordergraaf@deanconnect.nl)

All rights reserved by Dean Connect and Leo Noordergraaf."""


#----------------------
# imports
import SocketServer
import codecs
import time

#----------------------
# error-codes + exceptions

#JSON-RPC 2.0 error-codes
PARSE_ERROR           = -32700
INVALID_REQUEST       = -32600
METHOD_NOT_FOUND      = -32601
INVALID_METHOD_PARAMS = -32602  #invalid number/type of parameters
INTERNAL_ERROR        = -32603  #"all other errors"

#additional error-codes
PROCEDURE_EXCEPTION    = -32000
AUTHENTIFICATION_ERROR = -32001
PERMISSION_DENIED      = -32002
INVALID_PARAM_VALUES   = -32003

#human-readable messages
ERROR_MESSAGE = {
    PARSE_ERROR           : "Parse error.",
    INVALID_REQUEST       : "Invalid Request.",
    METHOD_NOT_FOUND      : "Method not found.",
    INVALID_METHOD_PARAMS : "Invalid parameters.",
    INTERNAL_ERROR        : "Internal error.",

    PROCEDURE_EXCEPTION   : "Procedure exception.",
    AUTHENTIFICATION_ERROR: "Authentification error.",
    PERMISSION_DENIED     : "Permission denied.",
    INVALID_PARAM_VALUES  : "Invalid parameter values."
}

#----------------------
# exceptions

class RPCError(Exception):
    """Base class for rpc-errors."""


class RPCTransportError(RPCError):
    """Transport error."""

class RPCTimeoutError(RPCTransportError):
    """Transport/reply timeout."""

class RPCFault(RPCError):
    """RPC error/fault package received.

    This exception can also be used as a class, to generate a
    RPC-error/fault message.

    :Variables:
        - error_code:   the RPC error-code
        - error_string: description of the error
        - error_data:   optional additional information
                        (must be json-serializable)
    :TODO: improve __str__
    """
    def __init__(self, error_code, error_message, error_data = None):
        RPCError.__init__(self)
        self.error_code   = error_code
        self.error_message = error_message
        self.error_data   = error_data

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return( "<RPCFault %s: %s (%s)>" % (self.error_code, repr(self.error_message), repr(self.error_data)) )

class RPCParseError(RPCFault):
    """Broken rpc-package. (PARSE_ERROR)"""
    def __init__(self, error_data = None):
        RPCFault.__init__(self, PARSE_ERROR, ERROR_MESSAGE[PARSE_ERROR], error_data)

class RPCInvalidRPC(RPCFault):
    """Invalid rpc-package. (INVALID_REQUEST)"""
    def __init__(self, error_data = None):
        RPCFault.__init__(self, INVALID_REQUEST, ERROR_MESSAGE[INVALID_REQUEST], error_data)

class RPCMethodNotFound(RPCFault):
    """Method not found. (METHOD_NOT_FOUND)"""
    def __init__(self, error_data = None):
        RPCFault.__init__(self, METHOD_NOT_FOUND, ERROR_MESSAGE[METHOD_NOT_FOUND], error_data)

class RPCInvalidMethodParams(RPCFault):
    """Invalid method-parameters. (INVALID_METHOD_PARAMS)"""
    def __init__(self, error_data = None):
        RPCFault.__init__(self, INVALID_METHOD_PARAMS, ERROR_MESSAGE[INVALID_METHOD_PARAMS], error_data)

class RPCInternalError(RPCFault):
    """Internal error. (INTERNAL_ERROR)"""
    def __init__(self, error_data = None):
        RPCFault.__init__(self, INTERNAL_ERROR, ERROR_MESSAGE[INTERNAL_ERROR], error_data)


class RPCProcedureException(RPCFault):
    """Procedure exception. (PROCEDURE_EXCEPTION)"""
    def __init__(self, error_data = None):
        RPCFault.__init__(self, PROCEDURE_EXCEPTION, ERROR_MESSAGE[PROCEDURE_EXCEPTION], error_data)

class RPCAuthentificationError(RPCFault):
    """AUTHENTIFICATION_ERROR"""
    def __init__(self, error_data = None):
        RPCFault.__init__(self, AUTHENTIFICATION_ERROR, ERROR_MESSAGE[AUTHENTIFICATION_ERROR], error_data)

class RPCPermissionDenied(RPCFault):
    """PERMISSION_DENIED"""
    def __init__(self, error_data = None):
        RPCFault.__init__(self, PERMISSION_DENIED, ERROR_MESSAGE[PERMISSION_DENIED], error_data)

class RPCInvalidParamValues(RPCFault):
    """INVALID_PARAM_VALUES"""
    def __init__(self, error_data = None):
        RPCFault.__init__(self, INVALID_PARAM_VALUES, ERROR_MESSAGE[INVALID_PARAM_VALUES], error_data)



#=========================================
# data structure / serializer

try:
    import simplejson
except ImportError, err:
    print "FATAL: json-module 'simplejson' is missing (%s)" % (err)
    sys.exit(1)


#----------------------
# JSON-RPC 1.0

class JsonRpc10:
    """JSON-RPC V1.0 data-structure / serializer

    This implementation is quite liberal in what it accepts: It treats
    missing "params" and "id" in Requests and missing "result"/"error" in
    Responses as empty/null.

    :SeeAlso:   JSON-RPC 1.0 specification
    :TODO:      catch simplejson.dumps not-serializable-exceptions
    """
    def __init__(self, dumps=simplejson.dumps, loads=simplejson.loads):
        """init: set serializer to use

        :Parameters:
            - dumps: json-encoder-function
            - loads: json-decoder-function
        :Note: The dumps_* functions of this class already directly create
               the invariant parts of the resulting json-object themselves,
               without using the given json-encoder-function.
        """
        self.dumps = dumps
        self.loads = loads


    def dumps_request(self, method, params=(), id = 0):
        """serialize JSON-RPC-Request

        :Parameters:
            - method: the method-name (str/unicode)
            - params: the parameters (list/tuple)
            - id:     if id=None, this results in a Notification
        :Returns:   | {"method": "...", "params": ..., "id": ...}
                    | "method", "params" and "id" are always in this order.
        :Raises:    TypeError if method/params is of wrong type or
                    not JSON-serializable
        """
        if not isinstance(method, (str, unicode)):
            raise TypeError('"method" must be a string (or unicode string).')

        if not isinstance(params, (tuple, list)):
            raise TypeError("params must be a tuple/list.")

        return '{"method": %s, "params": %s, "id": %s}' % \
            (self.dumps(method), self.dumps(params), self.dumps(id))


    def dumps_notification(self, method, params = ()):
        """serialize a JSON-RPC-Notification

        :Parameters: see dumps_request
        :Returns:   | {"method": "...", "params": ..., "id": null}
                    | "method", "params" and "id" are always in this order.
        :Raises:    see dumps_request
        """
        if not isinstance(method, (str, unicode)):
            raise TypeError('"method" must be a string (or unicode string).')
        if not isinstance(params, (tuple, list)):
            raise TypeError("params must be a tuple/list.")

        return '{"method": %s, "params": %s, "id": null}' % \
                (self.dumps(method), self.dumps(params))


    def dumps_response(self, result, id = None):
        """serialize a JSON-RPC-Response (without error)

        :Returns:   | {"result": ..., "error": null, "id": ...}
                    | "result", "error" and "id" are always in this order.
        :Raises:    TypeError if not JSON-serializable
        """
        error = 1
        try:
            result['error']
        except:
          error = 0

        if error:
            result = '{"result": null, "error": {"code":-10100, "message": "%s", "data": "Application error"}, "id": %s}' % \
                (result['error'], self.dumps(id))
        else:
            result = '{"result": %s, "error": null, "id": %s}' % \
                (self.dumps(result), self.dumps(id))
        return result


    def dumps_error(self, error, id = None):
        """serialize a JSON-RPC-Response-error

        Since JSON-RPC 1.0 does not define an error-object, this uses the
        JSON-RPC 2.0 error-object.

        :Parameters:
            - error: a RPCFault instance
        :Returns:   | {"result": null, "error": {"code": error_code, "message": error_message, "data": error_data}, "id": ...}
                    | "result", "error" and "id" are always in this order, data is omitted if None.
        :Raises:    ValueError if error is not a RPCFault instance,
                    TypeError if not JSON-serializable
        """
        if not isinstance(error, RPCFault):
            raise ValueError("""error must be a RPCFault-instance.""")

        if error.error_data is None:
            return '{"result": null, "error": {"code":%s, "message": %s}, "id": %s}' % \
                (self.dumps(error.error_code), self.dumps(error.error_message), self.dumps(id))
        else:
            return '{"result": null, "error": {"code":%s, "message": %s, "data": %s}, "id": %s}' % \
                (self.dumps(error.error_code), self.dumps(error.error_message), self.dumps(error.error_data), self.dumps(id))


    def loads_request(self, string):
        """de-serialize a JSON-RPC Request/Notification

        :Returns:   | [method_name, params, id] or [method_name, params]
                    | params is a tuple/list
                    | if id is missing, this is a Notification
        :Raises:    RPCParseError, RPCInvalidRPC, RPCInvalidMethodParams
        """
        try:
            data = self.loads(string)
        except ValueError, err:
            raise RPCParseError("No valid JSON. (%s)" % str(err))

        if not isinstance(data, dict):
            raise RPCInvalidRPC("No valid RPC-package.")

        if "method" not in data:
            raise RPCInvalidRPC("""Invalid Request, "method" is missing.""")

        if not isinstance(data["method"], (str, unicode)):
            raise RPCInvalidRPC("""Invalid Request, "method" must be a string.""")

        #if "id"     not in data:        data["id"]     = None   #be liberal # Bug fix: Teun, App hangs if id is not set
        if "id"     not in data:
            raise RPCInvalidRPC("""Invalid Request, "id" is missing.""")

        if "params" not in data:
            data["params"] = ()     #be liberal

        if not isinstance(data["params"], (list, tuple)):
            raise RPCInvalidRPC("""Invalid Request, "params" must be an array.""")

        if len(data) != 3:
            raise RPCInvalidRPC("""Invalid Request, additional fields found.""")

        # notification / request
        ## Bug fix: Teun, App hangs if id is not set
        #if data["id"] is None:
        #    return data["method"], data["params"]               #notification
        #else:
        return data["method"], data["params"], data["id"]   #request


    def loads_response(self, string):
        """de-serialize a JSON-RPC Response/error

        :Returns: | [result, id] for Responses
        :Raises:  | RPCFault+derivates for error-packages/faults, RPCParseError, RPCInvalidRPC
                  | Note that for error-packages which do not match the
                    V2.0-definition, RPCFault(-1, "Error", RECEIVED_ERROR_OBJ)
                    is raised.
        """
        try:
            data = self.loads(string)
        except ValueError, err:
            raise RPCParseError("No valid JSON. (%s)" % str(err))

        if not isinstance(data, dict):
            raise RPCInvalidRPC("No valid RPC-package.")

        if "id" not in data:
            raise RPCInvalidRPC("""Invalid Response, "id" missing.""")

        if "result" not in data:
            data["result"] = None    #be liberal


        if "error"  not in data:
            data["error"]  = None    #be liberal

        if len(data) != 3:
            raise RPCInvalidRPC("""Invalid Response, additional or missing fields.""")

        #error
        if data["error"] is not None:
            if data["result"] is not None:
                raise RPCInvalidRPC("""Invalid Response, one of "result" or "error" must be null.""")

            #v2.0 error-format
            if(
                isinstance(data["error"], dict)  and
                "code" in data["error"]  and
                "message" in data["error"]  and
                (   len(data["error"])==2 or
                    (   "data" in data["error"] and
                        len(data["error"]) == 3
                    )
                )
            ):
                if "data" not in data["error"]:
                    error_data = None
                else:
                    error_data = data["error"]["data"]

                if data["error"]["code"] == PARSE_ERROR:
                    raise RPCParseError(error_data)

                elif data["error"]["code"] == INVALID_REQUEST:
                    raise RPCInvalidRPC(error_data)

                elif data["error"]["code"] == METHOD_NOT_FOUND:
                    raise RPCMethodNotFound(error_data)

                elif data["error"]["code"] == INVALID_METHOD_PARAMS:
                    raise RPCInvalidMethodParams(error_data)

                elif data["error"]["code"] == INTERNAL_ERROR:
                    raise RPCInternalError(error_data)

                elif data["error"]["code"] == PROCEDURE_EXCEPTION:
                    raise RPCProcedureException(error_data)

                elif data["error"]["code"] == AUTHENTIFICATION_ERROR:
                    raise RPCAuthentificationError(error_data)

                elif data["error"]["code"] == PERMISSION_DENIED:
                    raise RPCPermissionDenied(error_data)

                elif data["error"]["code"] == INVALID_PARAM_VALUES:
                    raise RPCInvalidParamValues(error_data)

                else:
                    raise RPCFault(data["error"]["code"], data["error"]["message"], error_data)

            #other error-format
            else:
                raise RPCFault(-1, "Error", data["error"])

        #result
        else:
            return data["result"], data["id"]
