// SPDX-License-Identifier: MIT

pragma solidity ^0.8.0;

import "openzeppelin-solidity/contracts/token/ERC721/ERC721.sol";
import "openzeppelin-solidity/contracts/token/ERC721/extensions/IERC721Metadata.sol";
import "openzeppelin-solidity/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import "openzeppelin-solidity/contracts/token/ERC721/extensions/ERC721Burnable.sol";
import "openzeppelin-solidity/contracts/access/Ownable.sol";
import "openzeppelin-solidity/contracts/utils/math/SafeMath.sol";
import "openzeppelin-solidity/contracts/utils/Strings.sol";

import "https://github.com/ProjectOpenSea/opensea-creatures/blob/master/contracts/common/meta-transactions/ContentMixin.sol";
import "https://github.com/ProjectOpenSea/opensea-creatures/blob/master/contracts/common/meta-transactions/NativeMetaTransaction.sol";

contract OwnableDelegateProxy {}

contract ProxyRegistry {
    mapping(address => OwnableDelegateProxy) public proxies;
}

/**
 * @title ERC721Tradable
 * ERC721Tradable - ERC721 contract that whitelists a trading address, and has minting functionality.
 */
abstract contract ERC721Tradable is ContextMixin, ERC721URIStorage, NativeMetaTransaction, Ownable {
    using SafeMath for uint256;

    address proxyRegistryAddress;

    // Optional mapping for token URIs
    mapping (uint256 => string) private _tokenURIs;
    uint256[] _listOfTokens;
    mapping(address =>  uint256[]) private _OwnerHasToken;

    constructor(
        string memory _name,
        string memory _symbol,
        address _proxyRegistryAddress
    ) ERC721(_name, _symbol) {
        proxyRegistryAddress = _proxyRegistryAddress;
        _initializeEIP712(_name);
    }

    /**
     * @dev Mints a token to an address with a tokenURI.
     * @param _to address of the future owner of the token
     */
    /**
    * @dev Mints a token to an address with a tokenURI.
    * @param _to address of the future owner of the token
    */
     function mintTo(address _to, uint256 _id, string memory _uri) public onlyOwner {
        _mint(_to, _id);
        _setTokenURI(_id, _uri);
        _listOfTokens.push(_id);
        if(_OwnerHasToken[_to].length != 0){
            _OwnerHasToken[_to].push(_id);
        }else{
            _OwnerHasToken[_to] = [_id];
        }
    }

    /**
     * @dev See {IERC721-safeTransferFrom}.
     */
    function plotTransfer(
        address from,
        address to,
        uint256 tokenId
    ) public virtual{
        safeTransferFrom(from, to, tokenId);

        if(_OwnerHasToken[to].length != 0){
            _OwnerHasToken[to].push(tokenId);
        }else{
            _OwnerHasToken[to] = [tokenId];
        }

        for (uint index=0; index<_OwnerHasToken[from].length; index++) {
            if(_OwnerHasToken[from][index] == tokenId){
                _OwnerHasToken[from][index] = _OwnerHasToken[from][_OwnerHasToken[from].length-1];
                _OwnerHasToken[from].pop();
            }
        }
    }

    function getTokensByOwner(address owner) public view returns(uint256[] memory) {
        return  _OwnerHasToken[owner];
    }

    function getTokens() public view returns(uint[] memory) {
        return _listOfTokens;
    }


    /**
     * Override isApprovedForAll to whitelist user's OpenSea proxy accounts to enable gas-less listings.
     */
    function isApprovedForAll(address owner, address operator)
        override
        public
        view
        returns (bool)
    {
        // Whitelist OpenSea proxy contract for easy trading.
        ProxyRegistry proxyRegistry = ProxyRegistry(proxyRegistryAddress);
        if (address(proxyRegistry.proxies(owner)) == operator) {
            return true;
        }

        return super.isApprovedForAll(owner, operator);
    }

    /**
     * This is used instead of msg.sender as transactions won't be sent by the original token owner, but by OpenSea.
     */
    function _msgSender()
        internal
        override
        view
        returns (address sender)
    {
        return ContextMixin.msgSender();
    }

    /**
     * @dev Burns `tokenId`. See {ERC721-_burn}.
     *
     * Requirements:
     *
     * - The caller must own `tokenId` or be an approved operator.
     */
    function burn(uint256 tokenId) public virtual {
        //solhint-disable-next-line max-line-length
        require(_isApprovedOrOwner(_msgSender(), tokenId), "ERC721Burnable: caller is not owner nor approved");
        _burn(tokenId);
    }
}
