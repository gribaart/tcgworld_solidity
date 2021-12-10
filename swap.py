class CrossChainSwapSerializer(serializers.ModelSerializer):
    user_wallet_address = serializers.CharField(allow_null=True, max_length=245)
    source = serializers.CharField(allow_null=True, max_length=245)
    fee_transaction_address_source = serializers.CharField(allow_null=True, max_length=245)
    transaction_address_source = serializers.CharField(allow_null=True, max_length=245)
    target = serializers.CharField(allow_null=True, max_length=245)
    transaction_address_target = serializers.CharField(allow_null=True, max_length=245)
    value = serializers.CharField(allow_null=True, max_length=245)
    stage = serializers.CharField(allow_null=True, max_length=245)

    class Meta:
        model = CrossChainSwap
        fields = ['user_wallet_address', 'source', 'fee_transaction_address_source', 'transaction_address_source', 'target', 'transaction_address_target', 'value', 'stage']


class CrossChainSwapView(APIView):
    def post(self, request):
        serializer = CrossChainSwapSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Check that data in Swap Request Data is unique and the similar Swap Request does not exist.
        swap_fee_trx_exist = CrossChainSwap.objects.all().filter(
            fee_transaction_address_source=serializer.data.get("fee_transaction_address_source",None)).exists()

        erc20_trx_exist = CrossChainSwap.objects.all().filter(
            transaction_address_source=serializer.data.get("transaction_address_source", None)).exists()

        if swap_fee_trx_exist or erc20_trx_exist:
            return JsonResponse({
                "response": "Attempt to re-cross-chain transfer was prevented."
            })

        # If similar Swap Request does not exist in database, create new Swap Request record in database.
        swap = CrossChainSwap.objects.create(
            user_wallet_address=serializer.data.get("user_wallet_address", None),
            source=serializer.data.get("source", None),
            fee_transaction_address_source=serializer.data.get("fee_transaction_address_source", None),
            transaction_address_source=serializer.data.get("transaction_address_source", None),
            target=serializer.data.get("target", None),
            transaction_address_target=None,
            value=serializer.data.get("value", None),
            stage=CrossChainSwap.INITIAL,
        )

        # Next IF helps set correct Fee for checking Swap Request Data  based on Source Chain

        # 0.035 BNB ~ $15
        if swap.source == CrossChainSwap.BSC:
            eth_param = ""
            swap_fee = 0.035
            decimal = 10 ** 18
            blockchain = 'bsc'
        # 0.035 BNB ~ 0.005
        elif swap.source == CrossChainSwap.ETH:
            blockchain = "ethereum"
            # TODO: Remove test URL param
            eth_param = "?testnetType=ethereum-rinkeby"
            swap_fee = 0.005
            decimal = 10 ** 18

        w3 = Web3(HTTPProvider(
            "https://api-eu1.tatum.io/v3/" +
            blockchain + "/web3/" +
            TATUM_PRIVATE_KEY + eth_param)
        )

        transaction_hash = serializer.data.get("fee_transaction_address_source", None)
        transaction = w3.eth.getTransaction(transaction_hash)
        # Check if transaction exist
        if transaction.blockHash:
            swap.stage = CrossChainSwap.FEE_CHECK
            swap.save()
            # Check that trx fee value equals transfer fee on target blockchain
            # Check that fee trx reciever wallet equals Exchange Wallet
            # Check that fee trx sender wallet equals Client Wallet from Swap Request Data
            if (transaction.value / decimal) == swap_fee and \
                    transaction["to"].lower() == EXCHANGE_WALLET.lower() and \
                    transaction["from"].lower() == swap.user_wallet_address:
                swap.stage = CrossChainSwap.SOURCE_TRANSFER_CHECK
                swap.save()

                handler = CrossChainSwapHandler()
                # Setup handler on Source Chain to check the Client transaction (Client -> Exchange)
                handler.connectToProvider(swap.source)

                # Check that ERC20 trx was send to Exchange Wallet from Client Wallet on Source Chain from Swap Request Data
                if handler.check_smart_contract_transfer_trx(swap.transaction_address_source, swap.source,
                                                             swap.user_wallet_address, EXCHANGE_WALLET.lower(),
                                                             swap.value):
                    # Change handler's connection to Target Chain to send TCG2 for Echange Wallet to Client Wallet
                    # and check that transaction was accepted
                    handler.connectToProvider(swap.target)
                    swap.stage = CrossChainSwap.TARGET_TRANSFER
                    swap.save()
                    #Send TCG2 from Exchange wallet to Client Wallet on Source Chain
                    swap_trx = handler.swap(swap.user_wallet_address, swap.target, swap.value)

                    # Check that ERC20 trx was send from Exchange Wallet to Client Wallet on Target Chain from Swap Request Data
                    if handler.check_smart_contract_transfer_trx(swap_trx, swap.target, EXCHANGE_WALLET.lower(),
                                                                 swap.user_wallet_address,
                                                                 swap.value):
                        swap.stage = CrossChainSwap.COMPLETE
                        swap.save()
                        return JsonResponse({
                            "response": "Swap successfully complete."
                        })
                    else:
                        return JsonResponse({
                            "response": "TCG2 transaction was not send from Exchange Wallet to Client Wallet on Target Chain."
                        })
                else:
                    return JsonResponse({
                        "response": "TCG2 transaction transaction was not send to Exchange Wallet from Client Wallet on Source Chain."
                    })
            else:
                return JsonResponse({
                    "response": "Fee transaction values are not valid."
                })
        else:
            return JsonResponse({
                "response": "Fee transaction hash is not valid."
            })
