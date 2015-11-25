#!/usr/bin/php
<?php

require "../lib/jsonRpcClient.php";

$jsonrpc = new JsonRpcClient();
$jsonrpc->setHost('127.0.0.1');
$jsonrpc->setPort(3000);
$jsonrpc->setPrefix('test.');
$jsonrpc->setReconnect(true);
$jsonrpc->setDebug(true);

$call = "";
try {
    $call = $jsonrpc->Test(7, 8);
} catch (Exception $e) {
    print_r($e);
    exit(1);
}
echo "Succes\n";
print_r($call);
exit(0);

?>