jsonrpcclient-php - A php jsonrpc v1 library 
==============================================

JsonRPC v1 client written in PHP

Installing
----------

The easiest way to install **jsonrpcclient-php** is to use [Composer](http://getcomposer.org/download/), the awesome dependency manager for PHP. Once Composer is installed, run `composer.phar require nextpertise/jsonrpcclient-php:dev-master` and composer will do all the hard work for you.

Use
----------

    require 'vendor/autoload.php';
    
    use JsonRpcClient\JsonRpcClient;
    
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
