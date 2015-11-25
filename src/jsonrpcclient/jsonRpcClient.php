<?php

namespace Jsonrpcclient;

class JsonRpcException extends Exception {}
class JsonConnException extends JsonRpcException {}
class JsonOptException extends JsonRpcException {}
class JsonIOException extends JsonRpcException{}
class JsonEncodingException extends JsonRpcException{}

class JsonRpcClient
{
    private $socket = null;
    private $host = null;
    private $port = null;
    private $prefix = '';
    private $debug = false;
    private $connected = false;
    private $reconnect = false;
    private $timeout = 1; // seconds, integer

    // -----

    public function __construct()
    {
        $this->socket = NULL;
        $this->host = null;
        $this->port = null;
        $this->prefix = '';
        $this->debug = false;
        $this->connected = false;
        $this->reconnect = false;
        $this->timeout = 1;
    }

    public function __destruct()
    {
        $this->disconnect();
        $this->socket = null;
    }

    // -----

    /**
     * Connects the client to the server.
     * Requires that at the very least the host and port are set by calling setHost() and setPort().
     * The socket is set to timeout on read and write. The timeout period defaults to 1 second and can be
     * controlled by calling setTimeout() before calling connect().
     * @throw JsonConnException when the host and port are not defined or when the connection setup failed.
     * @return void
     */
    public function connect()
    {
        if (!$this->socket) {
            if ($this->host === null || $this->port === null) {
                throw new JsonConnException("Port or host not provided");
            }

            $this->socket = socket_create(AF_INET, SOCK_STREAM, SOL_TCP);

            if (!$this->socket) {
                throw new JsonConnException(socket_strerror(socket_last_error()));
            }

            if (!socket_set_option($this->socket, SOL_SOCKET, SO_RCVTIMEO, array("sec" => $this->timeout, "usec" => 0))) {
                throw new JsonOptException(socket_strerror(socket_last_error()));
            };

            if (!socket_set_option($this->socket, SOL_SOCKET, SO_SNDTIMEO, array("sec" => $this->timeout, "usec" => 0))) {
                throw new JsonOptException(socket_strerror(socket_last_error()));
            }

            if (!socket_connect($this->socket, $this->getHost(), $this->getPort())) {
                throw new JsonConnException(socket_strerror(socket_last_error()));
            }
        }
        $this->setConnected(true);
        return 0;
    }

    // -----

    /**
     * Disconnect the client from the server.
     */
    public function disconnect()
    {
        if ($this->socket) {
            socket_close($this->socket);
            $this->socket = null;
            $this->setConnected(false);
        }
    }

    // -----

    // alternative json_encode
    private function _json_encode($val)
    {
        if (is_string($val)) {
            return '"' . $this->_addslashes($val) . '"';
        }

        if (is_numeric($val)) {
            return $val;
        }

        if ($val === null) {
            return 'null';
        }

        if ($val === true) {
            return 'true';
        }

        if ($val === false) {
            return 'false';
        }

        $assoc = false;
        $i = 0;
        foreach ($val as $k => $v) {
            if ($k !== $i++){
                $assoc = true;
                break;
            }
        }

        $res = array();
        foreach ($val as $k => $v) {
            $v = $this->_json_encode($v);
            if ($assoc) {
                $k = '"' . $this->_addslashes($k) . '"';
                $v = $k . ':' . $v;
            }
            $res[] = $v;
        }
        $res = implode(',', $res);
        return ($assoc) ?
            '{' . $res . '}' :
            '[' . $res . ']';
    }

    // alternate _addslashes, don't add slashes to slashes
    private function _addslashes($string)
    {
        $string = addslashes($string);
        return str_replace('\\\\', '\\', $string);
    }

    // This function counts the curly brackets in the input string, and will return true if they match.
    private function checkJsonStream($str)
    {
        $curlybracketcounter = 0;
        $doubleqoute = $singleqoute = true;

        for ($i = 0; $i < strlen($str); $i++) {
            if ($singleqoute)
                if ($str[$i] == '"' && $str[$i-1] != '\\')
                    $doubleqoute = !$doubleqoute;

            if ($doubleqoute)
                if ($str[$i] == "'" && $str[$i-1] != '\\')
                    $singleqoute = !$singleqoute;

            if ($doubleqoute && $singleqoute) {
                if ($str[$i] == '{')
                    $curlybracketcounter++;

                if ($str[$i] == '}')
                    $curlybracketcounter--;
            }
        }
        return ($curlybracketcounter == 0);
    }

    /**
     * Sends the rpc request.
     * @param string $name  The name of the remote function
     * @param mixed $params function parameters, scalar, array or hash
     * @throws JsonIOException on timeout or other connection error
     * @throws JsonPartialException when only part of the request is transmitted
     * @return void
     */
    private function send($name, $params)
    {
        $result = $this->_json_encode($params);

        $result = $result == '""' ? "" : $result;
        $request = '{"method": "' . $this->getPrefix() . $name . '", "params": ' . $result . ', "id": 0}';

        if ($this->isDebug()) {
            echo $request . "\n";
        }

        $byteswritten = socket_write($this->socket, $request, strlen($request));
        if ($byteswritten === false) {
            throw new JsonIOException(socket_strerror(socket_last_error()));
        }

        if ($this->isDebug()) {
            echo 'Request(' . strlen($request) . '=' . $byteswritten . ') -> [' . $request . "]\n";
        }

        if ($byteswritten !== strlen($request)) {
            throw new JsonPartialException("Request only partially written (timeout?)");
        }
    }

    /**
     * Receives the rpc reply.
     * @throws JsonIOException on timeout or other connection error
     * @throws JsonEncodingException when the received reply is invalid json encoded
     * @return mixed hash containing error en result keys
     */
    private function receive()
    {
        $reply = "";
        do {
            $result = socket_recv($this->socket, $recv, 1024, 0);
            if ($result === false) {
                throw new JsonIOException(socket_strerror(socket_last_error()));
            }

            if($this->isDebug()) {
                echo 'Received(' . strlen($recv) . '=' . $result . ') -> [' . $recv . "]\n";
            }

            if ($recv != "") {
                $reply .= $recv;
            }

            // Check for continue
            $recv = rtrim($recv);
            if ($recv[strlen($recv) - 1] == "}") {
                $continue = !$this->checkJsonStream($reply);
            } else {
                $continue = true;
            }
        } while (!empty($recv) && $continue);

        $result = json_decode($reply);
        if ($result === null && json_last_error() !== JSON_ERROR_NONE) {
            throw new JsonEncodingException(json_last_error_msg());
        }

        // determine the return value, log it and finish
        return ($result == NULL ?
            array("error" => NULL, "result" => "-NULL") :
            array("error" => $result->error, "result" => $result->result));
    }

    /**
     * Calls the remote procedure.
     * Called as $object->FnName(arg1, arg2)
     * @param string $name The name of the remote function (FnName)
     * @param mixed Function call arguments (if any). Check the API documentation
     * to learn what arguments are required by a function.
     * @throws JsonIOException on timeout or other connection error
     * @throws JsonPartialException when only part of the request is transmitted
     * @throws JsonEncodingException when the received reply is invalid json encoded
     * @return mixed procedure call result.
     */
    public function __call($name, $params = "")
    {
        if ($this->isReconnect()) {
            $this->connect();
        }

        if (!$this->isConnected()) {
            throw new JsonConnException('RPC client is not yet connected, try $object->connect();');
        }

        $this->send($name, $params);
        $return = $this->receive();

        if ($this->isReconnect()) {
            $this->disconnect();
        }
        return $return;
    }

    // Private Setters
    private function setConnected($connected)
    {
        $this->connected = (bool)$connected;
    }

    // Getters & Setters
    /**
     * Returns the host to which the client connects.
     * @return string The name or ip address of the host.
     */
    public function getHost()
    {
        return $this->host;
    }

    /**
     * Sets the host to which the client will connect.
     * @param string $host The name or ip address of the host.
     * @return JsonRpcClient Support the fluent interface.
     */
    public function setHost($host)
    {
        $this->host = (string)$host;
        return $this;
    }

    /**
     * Returns the port number to which the client connects.
     * @return int Then port number of the connection.
     */
    public function getPort()
    {
        return $this->port;
    }

    /**
     * Sets the port to which the client will connect.
     * @param int $port The port number of the host.
     * @return JsonRpcClient Support the fluent interface.
     */
    public function setPort($port)
    {
        $this->port = (int)$port;
        return $this;
    }

    /**
     * Returns the function name prefix for the api.
     * @return string The function name prefix.
     */
    public function getPrefix()
    {
        return $this->prefix;
    }

    /**
     * Sets the function name prefix (api selector).
     * The function name prefix is combined with the function name to uniquely
     * identify a function.
     * @param string $prefix The function name prefix
     * @return JsonRpcClient Support the fluent interface.
     */
    public function setPrefix($prefix)
    {
        $this->prefix = (string)$prefix;
        return $this;
    }

    /**
     * Is the client in debug mode?
     * @return bool Debug flag
     */
    public function isDebug()
    {
        return $this->debug;
    }

    /**
     * Sets the debug flag.
     * @param bool $debug Set the debug flag to $debug.
     * @return JsonRpcClient Support the fluent interface.
     */
    public function setDebug($debug)
    {
        $this->debug = (bool)$debug;
        return $this;
    }

    /**
     * Is the client connected?
     * @return bool True when connected.
     */
    public function isConnected()
    {
        return $this->connected;
    }

    /**
     * Sets the reconnect flag.
     * When set (true) the client will connect/disconnect for each rpc request.
     * When unset (false) the client will reuse the open connection for multiple requests.
     * @param bool $reconnect
     * @return JsonRpcClient Support the fluent interface.
     */
    public function setReconnect($reconnect)
    {
        $this->reconnect = (bool)$reconnect;
        return $this;
    }

    /**
     * Get the reconnect flag.
     * @return bool The reconnect flag.
     */
    public function isReconnect()
    {
        return $this->reconnect;
    }

    /**
     * Get the read/write timeout.
     * @return int The read/write timeout in seconds.
     */
    public function getTimeout()
    {
        return $this->timeout;
    }

    /**
     * Sets the read/write timeout.
     * The default timeout value is 1 second.
     * Use this function to change this before calling Connect()
     * @param int $timeout The timeout in seconds
     * @return JsonRpcClient Support the fluent interface.
     */
    public function setTimeout($timeout)
    {
        $this->timeout = $timeout;
        return $this;
    }
}

?>
