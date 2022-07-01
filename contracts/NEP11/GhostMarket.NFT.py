from typing import Any, Dict, List, Union, cast

from boa3.builtin import CreateNewEvent, NeoMetadata, metadata, public
from boa3.builtin.contract import abort
from boa3.builtin.interop.blockchain import get_contract, Transaction
from boa3.builtin.interop.contract import GAS, call_contract, destroy_contract, update_contract, CallFlags
from boa3.builtin.interop.runtime import calling_script_hash, executing_script_hash, check_witness, script_container
from boa3.builtin.interop.stdlib import serialize, deserialize
from boa3.builtin.interop.storage import delete, get, put, find, get_read_only_context
from boa3.builtin.interop.storage.findoptions import FindOptions
from boa3.builtin.interop.iterator import Iterator
from boa3.builtin.type import UInt160, ByteString
from boa3.builtin.interop.json import json_deserialize
from boa3.builtin.interop.runtime import get_network


# -------------------------------------------
# METADATA
# -------------------------------------------

@metadata
def manifest_metadata() -> NeoMetadata:
    """
    Defines this smart contract's metadata information
    """
    meta = NeoMetadata()
    meta.author = "Mathias Enzensberger, Vincent Geneste"
    meta.description = "GhostMarket NFT"
    meta.email = "hello@ghostmarket.io"
    meta.supported_standards = ["NEP-11"]
    meta.source = ["https://github.com/OnBlockIO/n3-tokens-contracts/blob/master/contracts/NEP11/GhostMarket.NFT.py"]
    # meta.add_permission(contract='*', methods='*')
    return meta


# -------------------------------------------
# TOKEN SETTINGS
# -------------------------------------------

# Fee on deploy
MINT_FEE_ON_DEPLOY = 5_000_000  # initial mint fees of 0.05 GAS

# Symbol of the Token
TOKEN_SYMBOL = 'GHOST'

# Number of decimal places
TOKEN_DECIMALS = 0

# Whether the smart contract was deployed or not
DEPLOYED = b'deployed'

# Whether the smart contract is paused or not
PAUSED = b'paused'


# -------------------------------------------
# Prefixes
# -------------------------------------------

ACCOUNT_PREFIX = b'ACC'
TOKEN_PREFIX = b'TPF'
TOKEN_DATA_PREFIX = b'TDP'
LOCKED_PREFIX = b'LCP'
BALANCE_PREFIX = b'BLP'
SUPPLY_PREFIX = b'SPP'
META_PREFIX = b'MDP'
LOCKED_VIEW_COUNT_PREFIX = b'LVCP'
ROYALTIES_PREFIX = b'RYP'


# -------------------------------------------
# Keys
# -------------------------------------------

TOKEN_COUNT = b'TOKEN_COUNT'
MINT_FEE = b'MINT_FEE'
AUTH_ADDRESSES = b'AUTH_ADDRESSES'
WL_ADDRESSES = b'WITHLISTED'


# -------------------------------------------
# Events
# -------------------------------------------

on_transfer = CreateNewEvent(
    # trigger when tokens are transferred, including zero value transfers.
    [
        ('from_addr', Union[UInt160, None]),
        ('to_addr', Union[UInt160, None]),
        ('amount', int),
        ('tokenId', ByteString)
    ],
    'Transfer'
)

on_auth = CreateNewEvent(
    # trigger when an address has been authorized/whitelisted.
    [
        ('authorized', UInt160),
        ('type', int),
        ('add', bool),
    ],
    'Authorized'
)

on_withdraw_mint_fee = CreateNewEvent(
    # trigger when mint fees are withdrawn.
    [
        ('from_addr', UInt160),
        ('value', int)
    ],
    'MintFeeWithdrawn'
)

on_update_mint_fee = CreateNewEvent(
    # trigger when mint fees are updated.
    [
        ('from_addr', UInt160),
        ('value', int)
    ],
    'MintFeeUpdated'
)

on_unlock = CreateNewEvent(
    [
        ('tokenId', ByteString),
        ('counter', int)
    ],
    'UnlockIncremented'
)

# DEBUG_START
# -------------------------------------------
# DEBUG
# -------------------------------------------

debug = CreateNewEvent(
    [
        ('params', list),
    ],
    'Debug'
)

# DEBUG_END
# -------------------------------------------
# NEP-11 Methods
# -------------------------------------------


@public(safe=True)
def symbol() -> str:
    """
    Gets the symbols of the token.

    This string must be valid ASCII, must not contain whitespace or control characters, should be limited to uppercase
    Latin alphabet (i.e. the 26 letters used in English) and should be short (3-8 characters is recommended).
    This method must always return the same value every time it is invoked.

    :return: a short string representing symbol of the token managed in this contract.
    """
    debug(['symbol: ', TOKEN_SYMBOL])
    return TOKEN_SYMBOL


@public(safe=True)
def decimals() -> int:
    """
    Gets the amount of decimals used by the token.

    E.g. 8, means to divide the token amount by 100,000,000 (10 ^ 8) to get its user representation.
    This method must always return the same value every time it is invoked.

    :return: the number of decimals used by the token.
    """
    debug(['decimals: ', TOKEN_DECIMALS])
    return TOKEN_DECIMALS


@public(safe=True)
def totalSupply() -> int:
    """
    Gets the total token supply deployed in the system.

    This number must not be in its user representation. E.g. if the total supply is 10,000,000 tokens, this method
    must return 10,000,000 * 10 ^ decimals.

    :return: the total token supply deployed in the system.
    """
    return get(SUPPLY_PREFIX, get_read_only_context()).to_int()


@public(safe=True)
def balanceOf(owner: UInt160) -> int:
    """
    Get the current balance of an address

    The parameter owner must be a 20-byte address represented by a UInt160.

    :param owner: the owner address to retrieve the balance for
    :type owner: UInt160
    :return: the total amount of tokens owned by the specified address.
    :raise AssertionError: raised if `owner` length is not 20.
    """
    assert validateAddress(owner), "Not a valid address"
    debug(['balanceOf: ', get(mk_balance_key(owner), get_read_only_context()).to_int()])
    return get(mk_balance_key(owner), get_read_only_context()).to_int()


@public(safe=True)
def tokensOf(owner: UInt160) -> Iterator:
    """
    Get all of the token ids owned by the specified address

    The parameter owner must be a 20-byte address represented by a UInt160.

    :param owner: the owner address to retrieve the tokens for
    :type owner: UInt160
    :return: an iterator that contains all of the token ids owned by the specified address.
    :raise AssertionError: raised if `owner` length is not 20.
    """
    assert validateAddress(owner), "Not a valid address"
    flags = FindOptions.REMOVE_PREFIX | FindOptions.KEYS_ONLY
    context = get_read_only_context()
    return find(mk_account_key(owner), context, flags)


@public
def transfer(to: UInt160, tokenId: ByteString, data: Any) -> bool:
    """
    Transfers the token with id tokenId to address to

    The parameter to SHOULD be a 20-byte address. If not, this method SHOULD throw an exception.
    The parameter tokenId SHOULD be a valid NFT. If not, this method SHOULD throw an exception.
    If the method succeeds, it MUST fire the Transfer event, and MUST return true, even if the token is sent to the owner.
    If the receiver is a deployed contract, the function MUST call onNEP11Payment method on receiver contract with the
    data parameter from transfer AFTER firing the Transfer event.

    The function SHOULD check whether the owner address equals the caller contract hash. If so, the transfer SHOULD be
    processed; If not, the function SHOULD use the SYSCALL Neo.Runtime.CheckWitness to verify the transfer.

    If the transfer is not processed, the function SHOULD return false.

    :param to: the address to transfer to
    :type to: UInt160
    :param tokenId: the token to transfer
    :type tokenId: ByteString
    :param data: whatever data is pertinent to the onPayment method
    :type data: Any
    :return: whether the transfer was successful
    :raise AssertionError: raised if `to` length is not 20 or if `tokenId` is not a valid NFT or if the contract is paused.
    """
    assert validateAddress(to), "Not a valid address"
    assert not isPaused(), "GhostMarket contract is currently paused"
    token_owner = get_owner_of(tokenId)

    if not check_witness(token_owner):
        return False

    if (token_owner != to):
        set_balance(token_owner, -1)
        remove_token_account(token_owner, tokenId)

        set_balance(to, 1)

        set_owner_of(tokenId, to)
        add_token_account(to, tokenId)
    post_transfer(token_owner, to, tokenId, data)
    return True


def post_transfer(token_owner: Union[UInt160, None], to: Union[UInt160, None], tokenId: ByteString, data: Any):
    """
    Checks if the one receiving NEP11 tokens is a smart contract and if it's one the onPayment method will be called - internal

    :param token_owner: the address of the sender
    :type token_owner: UInt160
    :param to: the address of the receiver
    :type to: UInt160
    :param tokenId: the token hash asByteString 
    :type tokenId:ByteString 
    :param data: any pertinent data that might validate the transaction
    :type data: Any
    """
    on_transfer(token_owner, to, 1, tokenId)
    if not isinstance(to, None):
        contract = get_contract(to)
        if not isinstance(contract, None):
            call_contract(to, 'onNEP11Payment', [token_owner, 1, tokenId, data])
            pass


@public(safe=True)
def ownerOf(tokenId: ByteString) -> UInt160:
    """
    Get the owner of the specified token.

    The parameter tokenId SHOULD be a valid NFT. If not, this method SHOULD throw an exception.

    :param tokenId: the token for which to check the ownership
    :type tokenId: ByteString
    :return: the owner of the specified token.
    :raise AssertionError: raised if `tokenId` is not a valid NFT.
    """
    owner = get_owner_of(tokenId)
    debug(['ownerOf: ', owner])
    return owner


@public(safe=True)
def tokens() -> Iterator:
    """
    Get all tokens minted by the contract

    :return: an iterator that contains all of the tokens minted by the contract.
    """
    flags = FindOptions.REMOVE_PREFIX | FindOptions.KEYS_ONLY
    context = get_read_only_context()
    return find(TOKEN_PREFIX, context, flags)


@public(safe=True)
def properties(tokenId: ByteString) -> Dict[Any, Any]:
    """
    Get the properties of a token.

    The parameter tokenId SHOULD be a valid NFT. If no metadata is found (invalid tokenId), an exception is thrown.

    :param tokenId: the token for which to check the properties
    :type tokenId: ByteString
    :return: a serialized NVM object containing the properties for the given NFT.
    :raise AssertionError: raised if `tokenId` is not a valid NFT, or if no metadata available.
    """
    metaBytes = cast(str, get_meta(tokenId))
    assert len(metaBytes) != 0, 'No metadata available for token'
    metaObject = cast(Dict[str, str], json_deserialize(metaBytes))

    return metaObject


@public(safe=True)
def propertiesJson(tokenId: ByteString) -> ByteString:
    """
    Get the properties of a token.

    The parameter tokenId SHOULD be a valid NFT. If no metadata is found (invalid tokenId), an exception is thrown.

    :param tokenId: the token for which to check the properties
    :type tokenId: ByteString
    :return: a serialized NVM object containing the properties for the given NFT.
    :raise AssertionError: raised if `tokenId` is not a valid NFT, or if no metadata available.
    """
    meta = get_meta(tokenId)
    assert len(meta) != 0, 'No metadata available for token'
    debug(['properties: ', meta])
    return meta


@public
def _deploy(data: Any, upgrade: bool):
    """
    The contracts initial entry point, on deployment.
    """
    debug(["deploy now"])
    if upgrade:
        return

    if get(DEPLOYED, get_read_only_context()).to_bool():
        return

    tx = cast(Transaction, script_container)
    debug(["tx.sender: ", tx.sender, get_network()])
    owner: UInt160 = tx.sender
    network = get_network()
# DEBUG_START
# custom owner for tests, ugly hack, because TestEnginge sets an unkown tx.sender...
    if data is not None and network == 860833102:
        newOwner = cast(UInt160, data)
        debug(["check", newOwner])
        internal_deploy(newOwner)
        return
    # else:
        # owner = tx.sender

    if data is None and network == 860833102:
        return
    # if tx.sender == UInt160(b'\x9c\xa5/\x04"{\xf6Z\xe2\xe5\xd1\xffe\x03\xd1\x9dd\xc2\x9cF'):
    # owner = UInt160('\x96Wl\x0e**\x1c!\xc4\xac^\xbd)31\x15%A\x1f@')
# DEBUG_END
    debug(["owner: ", owner])
    internal_deploy(owner)


def internal_deploy(owner: UInt160):

    put(DEPLOYED, True)
    put(PAUSED, False)
    put(TOKEN_COUNT, 0)
    put(MINT_FEE, MINT_FEE_ON_DEPLOY)

    auth: List[UInt160] = []
    auth.append(owner)
    serialized = serialize(auth)
    put(AUTH_ADDRESSES, serialized)

    wl: List[UInt160] = []
    wl.append(owner)
    wl_serialized = serialize(auth)
    put(WL_ADDRESSES, wl_serialized)


@public
def onNEP17Payment(from_address: UInt160, amount: int, data: Any):
    """
    :param from_address: the address of the one who is trying to send cryptocurrency to this smart contract
    :type from_address: UInt160
    :param amount: the amount of cryptocurrency that is being sent to the this smart contract
    :type amount: int
    :param data: any pertinent data that might validate the transaction
    :type data: Any
    """
    if calling_script_hash != GAS:
        abort()
    assert amount > 0, "amount has to be > 0"
    debug(["onNEP17Payment", data])


# -------------------------------------------
# GhostMarket Methods
# -------------------------------------------

@public
def burn(tokenId: ByteString) -> bool:
    """
    Burn a token.

    :param tokenId: the token to burn
    :type tokenId: ByteString
    :return: whether the burn was successful.
    :raise AssertionError: raised if the contract is paused.
    """
    assert not isPaused(), "GhostMarket contract is currently paused"
    return internal_burn(tokenId)


@public
def multiBurn(tokens: List[ByteString]) -> List[bool]:
    """
    Burn multiple tokens.

    :param tokens: list of tokens to burn
    :type tokens: ByteString list
    :return: whether each burn was successful, as a list.
    """
    burned: List[bool] = []
    for i in tokens:
        burned.append(burn(i))
    return burned


@public
def mint(account: UInt160, meta: ByteString, lockedContent: ByteString, royalties: ByteString) -> ByteString:
    """
    Mint new token.

    :param account: the address of the account that is minting token
    :type account: UInt160
    :param meta: the metadata to use for this token
    :type meta:ByteString 
    :param lockedContent: the lock content to use for this token
    :type lockedContent:ByteString 
    :param royalties: the royalties to use for this token
    :type royalties:ByteString 
    :param data: whatever data is pertinent to the mint method
    :type data: Any
    :return: tokenId of the token minted
    :raise AssertionError: raised if mint fee is less than than 0 or if the account does not have enough to pay for it or if the contract is paused or if check witness fails.
    """
    assert validateAddress(account), "Not a valid address"  # not really necessary because check_witness would catch an invalid address
    assert not isPaused(), "GhostMarket contract is currently paused"

    fee = get_mint_fee()
    assert fee >= 0, "Mint fee can't be < 0"
    assert check_witness(account), "Invalid witness" 

    if fee > 0:
        success: bool = call_contract(GAS, 'transfer', [account, executing_script_hash, fee, None])
        assert success, "Fee payment failed!" 

    return internal_mint(account, meta, lockedContent, royalties)


@public
def multiMint(account: UInt160, meta: List[ByteString], lockedContent: List[ByteString], royalties: List[ByteString]) -> List[ByteString]:
    """
    Mint new tokens.

    :param account: the address of the account that is minting tokens
    :type account: UInt160
    :param meta: the metadata to use for this token
    :type meta:ByteString 
    :param lockedContent: the lock content to use for this token
    :type lockedContent:ByteString 
    :param royalties: the royalties to use for this token
    :type royalties:ByteString 
    :return: list of tokenId of the tokens minted
    :raise AssertionError: raised if royalties or lockContent or meta is not a list
    """
    assert isinstance(meta, list), "meta format should be a list!"
    assert isinstance(lockedContent, list), "lock content format should be a list!"
    assert isinstance(royalties, list), "royalties format should be a list!"

    nfts: List[ByteString] = []
    for i in range(0, len(meta)):
        nfts.append(mint(account, meta[i], lockedContent[i], royalties[i]))
    return nfts


@public
def mintWhitelisted(account: UInt160, meta: ByteString, lockedContent: ByteString, royalties: ByteString) -> ByteString:
    """
    Mint new token with no fees - whitelisted only.

    :param account: the address of the account that is minting token
    :type account: UInt160
    :param meta: the metadata to use for this token
    :type meta: bytes
    :param lockedContent: the lock content to use for this token
    :type lockedContent: bytes
    :param royalties: the royalties to use for this token
    :type royalties: bytes
    :return: tokenId of the token minted
    :raise AssertionError: raised if address is not whitelisted or if contract is paused
    """
    assert not isPaused(), "GhostMarket contract is currently paused"
    assert isWhitelisted(), '`account` is not whitelisted for mintWhitelisted'

    return internal_mint(account, meta, lockedContent, royalties)

@public(safe=True)
def getRoyalties(tokenId: ByteString) -> ByteString:
    """
    Get a token royalties values.

    :param tokenId: the token to get royalties values
    :type tokenId: ByteString
    :return: bytes of addresses and values for this token royalties.
    :raise AssertionError: raised if any `tokenId` is not a valid NFT.
    """
    royalties = get_royalties(tokenId)
    debug(['getRoyalties: ', royalties])
    return royalties


@public
def withdrawFee(account: UInt160) -> bool:
    """
    Withdraw mint fees.

    :param account: the address of the account that is withdrawing fees
    :type account: UInt160
    :return: whether the transaction was successful.
    :emits MintFeeWithdrawn: on success emits MintFeeWithdrawn
    :raise AssertionError: raised if witness is not verified.
    """
    assert verify(), '`acccount` is not allowed for withdrawFee'
    assert validateAddress(account), "Not a valid address"
    current_balance = cast(int, call_contract(GAS, 'balanceOf', [executing_script_hash], CallFlags.READ_ONLY))
    on_withdraw_mint_fee(account, current_balance)
    debug(['withdrawFee: ', current_balance])

    status: bool = call_contract(GAS, 'transfer', [executing_script_hash, account, current_balance, None])
    return status


@public(safe=True)
def getFeeBalance() -> Any:
    """
    Get mint fees balance.

    :return: balance of mint fees.
    """
    balance = call_contract(GAS, 'balanceOf', [executing_script_hash], CallFlags.READ_ONLY)
    debug(['getFeeBalance: ', balance])
    return balance


@public(safe=True)
def getMintFee() -> int:
    """
    Get configured mint fees value.

    :return: value of mint fees.
    """
    fee = get_mint_fee()
    debug(['getMintFee: ', fee])
    return fee


@public
def setMintFee(fee: int):
    """
    Set mint fees value.

    :param fee: fee to be used when minting
    :type fee: int
    :raise AssertionError: raised if witness is not verified.
    :emits MintFeeUpdated
    """
    assert verify(), '`acccount` is not allowed for setMintFee'
    assert fee >= 0, "fee has to be >= 0"
    set_mint_fee(fee)
    on_update_mint_fee(calling_script_hash, fee)


@public(safe=True)
def getLockedContentViewCount(tokenId: ByteString) -> int:
    """
    Get lock content view count of a token.

    :param tokenId: the token to query
    :type tokenId: ByteString
    :return: number of times the lock content of this token was accessed.
    """
    debug(['getLockedContentViewCount: ', get_locked_view_counter(tokenId)])
    return get_locked_view_counter(tokenId)


@public
def getLockedContent(tokenId: ByteString) -> ByteString:
    """
    Get lock content of a token.

    :param tokenId: the token to query
    :type tokenId: ByteString
    :return: the lock content of this token.
    :raise AssertionError: raised if witness is not owner
    :emits UnlockIncremented
    """
    owner = get_owner_of(tokenId)

    assert check_witness(owner), "Prohibited access to locked content!"
    set_locked_view_counter(tokenId)
    
    debug(['getLockedContent: ', get_locked_content(tokenId)])
    content = get_locked_content(tokenId)
    counter = get_locked_view_counter(tokenId)
    on_unlock(tokenId, counter)
    return content


@public(safe=True)
def getAuthorizedAddress() -> list[UInt160]:
    """
    Configure authorized addresses.

    When this contract address is included in the transaction signature,
    this method will be triggered as a VerificationTrigger to verify that the signature is correct.
    For example, this method needs to be called when withdrawing token from the contract.

    :param address: the address of the account that is being authorized
    :type address: UInt160
    :param authorized: authorization status of this address
    :type authorized: bool
    :return: whether the transaction signature is correct
    :raise AssertionError: raised if witness is not verified.
    """
    serialized = get(AUTH_ADDRESSES, get_read_only_context())
    auth = cast(list[UInt160], deserialize(serialized))

    return auth


@public
def setAuthorizedAddress(address: UInt160, authorized: bool):
    """
    Configure authorized addresses.

    When this contract address is included in the transaction signature,
    this method will be triggered as a VerificationTrigger to verify that the signature is correct.
    For example, this method needs to be called when withdrawing token from the contract.

    :param address: the address of the account that is being authorized
    :type address: UInt160
    :param authorized: authorization status of this address
    :type authorized: bool
    :return: whether the transaction signature is correct
    :raise AssertionError: raised if witness is not verified.
    """
    assert verify(), '`acccount` is not allowed for setAuthorizedAddress'
    assert validateAddress(address), "Not a valid address"
    assert isinstance(authorized, bool), "authorized has to be of type bool"
    serialized = get(AUTH_ADDRESSES, get_read_only_context())
    auth = cast(list[UInt160], deserialize(serialized))

    if authorized:
        found = False
        for i in auth:
            if i == address:
                found = True
                break

        if not found:
            auth.append(address)

        put(AUTH_ADDRESSES, serialize(auth))
        on_auth(address, 0, True)
    else:
        auth.remove(address)
        put(AUTH_ADDRESSES, serialize(auth))
        on_auth(address, 0, False)


@public
def setWhitelistedAddress(address: UInt160, authorized: bool):
    """
    Configure whitelisted addresses.

    When this contract address is included in the transaction signature,
    this method will be triggered as a VerificationTrigger to verify that the signature is correct.
    For example, this method needs to be called when using the no fee mint method.

    :param address: the address of the account that is being authorized
    :type address: UInt160
    :param authorized: authorization status of this address
    :type authorized: bool
    :return: whether the transaction signature is correct
    :raise AssertionError: raised if witness is not verified.
    """
    assert verify(), '`acccount` is not allowed for setWhitelistedAddress'
    assert validateAddress(address), "Not a valid address"
    assert isinstance(authorized, bool), "authorized has to be of type bool"
    serialized = get(WL_ADDRESSES, get_read_only_context())
    auth = cast(list[UInt160], deserialize(serialized))

    if authorized:
        found = False
        for i in auth:
            if i == address:
                found = True

        if not found:
            auth.append(address)

        put(WL_ADDRESSES, serialize(auth))
        on_auth(address, 1, True)
    else:
        auth.remove(address)
        put(WL_ADDRESSES, serialize(auth))
        on_auth(address, 1, False)


@public
def updatePause(status: bool) -> bool:
    """
    Set contract pause status.

    :param status: the status of the contract pause
    :type status: bool
    :return: the contract pause status
    :raise AssertionError: raised if witness is not verified.
    """
    assert verify(), '`acccount` is not allowed for updatePause'
    assert isinstance(status, bool), "status has to be of type bool"
    put(PAUSED, status)
    debug(['updatePause: ', get(PAUSED, get_read_only_context()).to_bool()])
    return get(PAUSED, get_read_only_context()).to_bool() 


@public
def verify() -> bool:
    """
    Check if the address is allowed.

    When this contract address is included in the transaction signature,
    this method will be triggered as a VerificationTrigger to verify that the signature is correct.
    For example, this method needs to be called when withdrawing token from the contract.

    :return: whether the transaction signature is correct
    """
    serialized = get(AUTH_ADDRESSES, get_read_only_context())
    auth = cast(list[UInt160], deserialize(serialized))
    tx = cast(Transaction, script_container)
    for addr in auth: 
        if check_witness(addr):
            debug(["Verification successful", addr, tx.sender])
            return True

    debug(["Verification failed", addr])
    return False


@public(safe=True)
def isWhitelisted() -> bool:
    """
    Check if the address is allowed to mint without fees.

    If the address is whitelisted, it's allowed to mint without any fees.

    :return: whether the address is allowed to mint without fees
    """
    serialized = get(WL_ADDRESSES, get_read_only_context())
    auth = cast(list[UInt160], deserialize(serialized))
    for addr in auth: 
        if check_witness(addr):
            debug(["Verification successful", addr])
            return True

    debug(["Verification failed", addr])
    return False


@public(safe=True)
def isPaused() -> bool:
    """
    Get the contract pause status.

    If the contract is paused, some operations are restricted.

    :return: whether the contract is paused
    """
    debug(['isPaused: ', get(PAUSED).to_bool()])
    if get(PAUSED, get_read_only_context()).to_bool():
        return True
    return False


@public
def update(script: bytes, manifest: bytes):
    """
    Upgrade the contract.

    :param script: the contract script
    :type script:ByteString 
    :param manifest: the contract manifest
    :type manifest:ByteString 
    :raise AssertionError: raised if witness is not verified
    """
    assert verify(), '`acccount` is not allowed for update'
    update_contract(script, manifest) 
    debug(['update called and done'])


@public
def destroy():
    """
    Destroy the contract.

    :raise AssertionError: raised if witness is not verified
    """
    assert verify(), '`acccount` is not allowed for destroy'
    destroy_contract() 
    debug(['destroy called and done'])


def internal_burn(tokenId: ByteString) -> bool:
    """
    Burn a token - internal

    :param tokenId: the token to burn
    :type tokenId: ByteString
    :return: whether the burn was successful.
    :raise AssertionError: raised if `tokenId` is not a valid NFT.
    """
    owner = get_owner_of(tokenId)

    if not check_witness(owner):
        return False

    remove_owner_of(tokenId)
    set_balance(owner, -1)
    add_to_supply(-1)
    remove_meta(tokenId)
    remove_locked_content(tokenId)
    remove_royalties(tokenId)
    remove_token_account(owner, tokenId)
    
    post_transfer(owner, None, tokenId, None)
    return True


def internal_mint(account: UInt160, meta: ByteString, lockedContent: ByteString, royalties: ByteString) -> ByteString:
    """
    Mint new token - internal

    :param account: the address of the account that is minting token
    :type account: UInt160
    :param meta: the metadata to use for this token
    :type meta:ByteString 
    :param lockedContent: the lock content to use for this token
    :type lockedContent:ByteString 
    :param royalties: the royalties to use for this token
    :type royalties:ByteString 
    :return: tokenId of the token minted
    :raise AssertionError: raised if meta is empty, or if contract is paused.
    """
    assert len(meta) != 0, '`meta` can not be empty'

    tokenId = get(TOKEN_COUNT, get_read_only_context()).to_int() + 1
    put(TOKEN_COUNT, tokenId)
    tokenIdBytes = tokenId.to_bytes()

    set_owner_of(tokenIdBytes, account)
    set_balance(account, 1)
    add_to_supply(1)

    add_meta(tokenIdBytes, meta)
    debug(['metadata: ', meta])

    if len(lockedContent) != 0:
        add_locked_content(tokenIdBytes, lockedContent)
        debug(['locked: ', lockedContent])

    if len(royalties) != 0:
        add_royalties(tokenIdBytes, cast(str, royalties))
        debug(['royalties: ', royalties])

    add_token_account(account, tokenIdBytes)
    post_transfer(None, account, tokenIdBytes, None)
    return tokenIdBytes


def remove_token_account(holder: UInt160, tokenId: ByteString):
    key = mk_account_key(holder) + tokenId
    debug(['add_token_account: ', key, tokenId])
    delete(key)


def add_token_account(holder: UInt160, tokenId: ByteString):
    key = mk_account_key(holder) + tokenId
    debug(['add_token_account: ', key, tokenId])
    put(key, tokenId)


def get_owner_of(tokenId: ByteString) -> UInt160:
    key = mk_token_key(tokenId)
    debug(['get_owner_of: ', key, tokenId])
    owner = get(key, get_read_only_context())
    return UInt160(owner)


def remove_owner_of(tokenId: ByteString):
    key = mk_token_key(tokenId)
    debug(['remove_owner_of: ', key, tokenId])
    delete(key)


def set_owner_of(tokenId: ByteString, owner: UInt160):
    key = mk_token_key(tokenId)
    debug(['set_owner_of: ', key, tokenId])
    put(key, owner)


def set_mint_fee(amount: int):
    debug(['set_mint_fee: ', amount])
    put(MINT_FEE, amount)


def add_to_supply(amount: int):
    total = totalSupply() + (amount)
    debug(['add_to_supply: ', amount])
    put(SUPPLY_PREFIX, total)


def set_balance(owner: UInt160, amount: int):
    old = balanceOf(owner)
    new = old + (amount)
    debug(['set_balance: ', amount])

    key = mk_balance_key(owner)
    if (new > 0):
        put(key, new)
    else:
        delete(key)


def get_meta(tokenId: ByteString) -> ByteString:
    key = mk_meta_key(tokenId)
    debug(['get_meta: ', key, tokenId])
    val = get(key, get_read_only_context())
    return val


def remove_meta(tokenId: ByteString):
    key = mk_meta_key(tokenId)
    debug(['remove_meta: ', key, tokenId])
    delete(key)


def add_meta(tokenId: ByteString, meta: ByteString):
    key = mk_meta_key(tokenId)
    debug(['add_meta: ', key, tokenId])
    put(key, meta)


def get_locked_content(tokenId: ByteString) -> ByteString:
    key = mk_locked_key(tokenId)
    debug(['get_locked_content: ', key, tokenId])
    val = get(key, get_read_only_context())
    return val


def remove_locked_content(tokenId: ByteString):
    key = mk_locked_key(tokenId)
    debug(['remove_locked_content: ', key, tokenId])
    delete(key)


def add_locked_content(tokenId: ByteString, content: ByteString):
    key = mk_locked_key(tokenId)
    debug(['add_locked_content: ', key, tokenId])
    put(key, content)


def get_royalties(tokenId: ByteString) -> ByteString:
    key = mk_royalties_key(tokenId)
    debug(['get_royalties: ', key, tokenId])
    val = get(key, get_read_only_context())
    return val


def add_royalties(tokenId: ByteString, royalties: str):
    key = mk_royalties_key(tokenId)
    debug(['add_royalties: ', key, tokenId])
    put(key, royalties)


def remove_royalties(tokenId: ByteString):
    key = mk_royalties_key(tokenId)
    debug(['remove_royalties: ', key, tokenId])
    delete(key)


def get_locked_view_counter(tokenId: ByteString) -> int:
    key = mk_lv_key(tokenId)
    debug(['get_locked_view_counter: ', key, tokenId])
    return get(key, get_read_only_context()).to_int()


def remove_locked_view_counter(tokenId: ByteString):
    key = mk_lv_key(tokenId)
    debug(['remove_locked_view_counter: ', key, tokenId])
    delete(key)


def set_locked_view_counter(tokenId: ByteString):
    key = mk_lv_key(tokenId)
    debug(['set_locked_view_counter: ', key, tokenId])
    count = get(key, get_read_only_context()).to_int() + 1
    put(key, count)


def get_mint_fee() -> int:
    fee = get(MINT_FEE, get_read_only_context())
    debug(['get_mint_fee: ', fee])
    return fee.to_int()


# helpers

@public
def validateAddress(address: UInt160) -> bool:
    if not isinstance(address, UInt160):
        return False
    if address == 0:
        return False
    return True


def mk_account_key(address: UInt160) -> ByteString:
    return ACCOUNT_PREFIX + address


def mk_balance_key(address: UInt160) -> ByteString:
    return BALANCE_PREFIX + address


def mk_token_key(tokenId: ByteString) -> ByteString:
    return TOKEN_PREFIX + tokenId


def mk_token_data_key(tokenId: ByteString) -> ByteString:
    return TOKEN_DATA_PREFIX + tokenId


def mk_meta_key(tokenId: ByteString) -> ByteString:
    return META_PREFIX + tokenId


def mk_locked_key(tokenId: ByteString) -> ByteString:
    return LOCKED_PREFIX + tokenId


def mk_royalties_key(tokenId: ByteString) -> ByteString:
    return ROYALTIES_PREFIX + tokenId


def mk_lv_key(tokenId: ByteString) -> ByteString:
    return LOCKED_VIEW_COUNT_PREFIX + tokenId
