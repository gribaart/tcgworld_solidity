# Off-chain Django database model of Swap Request

class CrossChainSwap(models.Model):
    INITIAL = "INITIAL"
    FEE_CHECK = "FEE_CHECK"
    SOURCE_TRANSFER_CHECK = "SOURCE_TRANSFER_CHECK"
    TARGET_TRANSFER = "TARGET_TRANSFER"
    COMPLETE = "COMPLETE"
    BSC = "bsc"
    ETH = "eth"

    STATUS = (
        (INITIAL, 'INIT'),
        (FEE_CHECK, 'FEE'),
        (SOURCE_TRANSFER_CHECK, 'SOURCE'),
        (TARGET_TRANSFER, 'TARGET'),
        (COMPLETE, 'COMPLETE'),
    )

    BLOCKCHAIN = (
        (BSC, 'BSC'),
        (ETH, 'ETH'),
    )


    EXCHANGE_WALLET = "EXCHANGE_WALLET_ADDRESS"

    user_wallet_address = models.CharField(null=True, max_length=256)
    fee_transaction_address_source = models.CharField(null=True, max_length=256)

    source = models.CharField(choices=BLOCKCHAIN, default=None, null=True)
    transaction_address_source = models.CharField(null=True, max_length=256)

    target = models.CharField(choices=BLOCKCHAIN, default=None, null=True)
    transaction_address_target = models.CharField(null=True, max_length=256)

    value = models.CharField(null=True, max_length=256)
    
    #initial, fee_check, source_transfer_check, target_transfer, complete
    stage = models.CharField(choices=STATUS, default=INITIAL)

# Off-chain Django database model of Binance Smart Chain Nonce on Exchange Wallet
    
class SwapNonceBSC(models.Model):
    OFFSET = 21
    nonce = models.IntegerField(default=0)

# Off-chain Django database model of Ethereum Nonce on Exchange Wallet

class SwapNonceETH(models.Model):
    OFFSET = 20
    nonce = models.IntegerField(default=0)
    
    
# Class that contains off-chain interaction logic with other side contract

class CrossChainSwapHandler:
    BSC = "bsc"
    ETH = "eth"
    BSC_GAS_PRICE = 15000000000
    GAS = 9000000
    TCG2_DECIMAL = 1000000000
    owner_wallet = None
    client_wallet = None
    contract_source = None
    source_chain_id = None
    contract_target = None
    target_chain_id = None
    w3 = None
    http_provider = None

    # Send ERC20 trx from exchange wallet to client wallet based on Swap Request Data
    def swap(self, client_wallet, blockchain, value):
        contract, chain_id = self.get_contract(blockchain)
        value_with_decimal = int(float(value) * self.TCG2_DECIMAL )

        if blockchain == self.BSC:
            gas_price = self.BSC_GAS_PRICE
            nonce_instace = SwapNonceBSC.bjects.create()
            nonce = nonce_instace.id + SwapNonceBSC.OFFSET
        elif blockchain == self.ETH:
            gas_price = int(self.w3.eth.generate_gas_price() * 2)
            nonce_instace = SwapNonceETH.bjects.create()
            nonce = nonce_instace.id + SwapNonceETH.OFFSET

        try:
            tx_dict = contract.functions.transfer(Web3.toChecksumAddress(client_wallet), value_with_decimal).buildTransaction({
                'chainId': chain_id,
                'gas': self.GAS,
                'gasPrice': gas_price,
                'nonce': nonce.nonce,
            })
            signed_tx = self.w3.eth.account.sign_transaction(tx_dict)
            tx_hash = self.w3.eth.sendRawTransaction(signed_tx.rawTransaction)
            tx_hash_str = self.w3.toHex(tx_hash)
            tx_receipt = self.w3.eth.waitForTransactionReceipt(tx_hash_str, timeout=120, poll_latency=0.1)
            return tx_hash
        except Exception as e:
            print(e)

    def check_smart_contract_transfer_trx(self, transaction_hash, blockchain, source_wallet, target_wallet, value=None):
        transaction = self.w3.eth.getTransaction(transaction_hash)
        contract, chain_id = self.get_contract(blockchain)
        func_obj, func_params = contract.decode_function_input(transaction.input)
        return func_params["amount"] == (int(float(value) * 10**9)) and \
               transaction["from"].lower() == source_wallet.lower() and \
                transaction["to"].lower() == target_wallet.lower()

    def get_contract(self, blockchain):
        ETH = 1
        ETH_TESTNET = 4
        BSC = 56
        BSC_TESTNET = 97

        if blockchain == self.BSC:
            ABI = bscABI
            address = BSC_COIN_CONTRACT_ADDRESS
            chain_id = BSC_TESTNET
        elif blockchain == self.ETH:
            ABI = ethABI
            address = ETH_COIN_CONTRACT_ADDRESS
            chain_id = ETH_TESTNET

        return self.w3.eth.contract(address=address, abi=ABI), chain_id

    def connectToProvider(self, blockchain):
        if blockchain == self.BSC:
            eth_param = ""
        if blockchain == self.ETH:
            blockchain = "ethereum"
            eth_param = "?testnetType=ethereum-rinkeby"
        self.w3 = Web3(HTTPProvider("https://api-eu1.tatum.io/v3/" +
                                    blockchain + "/web3/" + eth_param)
                       )
        self.w3.eth.set_gas_price_strategy(fast_gas_price_strategy)
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)

    def get_nonce(self):
        return self.w3.eth.getTransactionCount(Web3.toChecksumAddress(OWNER_COIN_CONTRACT_WALLET))
      

# Class that contains validation logic fo Swap Request and handling other side contract

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
            blockchain + "/web3/" + eth_param)
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
