<?php
# LocalSettings.php for Legacy Wiki (read-only review instance)
# Auto-generated for documentation migration project

# Protect against web entry
if ( !defined( 'MEDIAWIKI' ) ) {
    exit;
}

## General settings
$wgSitename = "DreamFactory Wiki (Legacy)";
$wgMetaNamespace = "DreamFactory_Wiki";

## Server and paths — auto-detect so it works from localhost, IP, or DNS
$wgServer = WebRequest::detectServer();
$wgScriptPath = "";
$wgArticlePath = "/index.php/$1";

## Database settings
$wgDBtype = "mysql";
$wgDBserver = "legacy-wiki-db";
$wgDBname = "df_wiki";
$wgDBuser = "wiki_user";
$wgDBpassword = "wiki_pass";
$wgDBprefix = "";
$wgDBTableOptions = "ENGINE=InnoDB, DEFAULT CHARSET=binary";

## Shared memory / caching
$wgMainCacheType = CACHE_NONE;
$wgMemCachedServers = [];

## Security / keys (not important for local review instance)
$wgSecretKey = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2";
$wgUpgradeKey = "a1b2c3d4e5f6a1b2";

## File uploads
$wgEnableUploads = false;

## Skin
wfLoadSkin( 'Vector' );
$wgDefaultSkin = "vector";

## Make it read-only for safety
$wgReadOnly = "This is a legacy archive for content review only.";

## Disable user registration
$wgGroupPermissions['*']['createaccount'] = false;
$wgGroupPermissions['*']['edit'] = false;

## Language
$wgLanguageCode = "en";

## Debug (disable for production)
$wgShowExceptionDetails = true;
$wgShowDBErrorBacktrace = true;
