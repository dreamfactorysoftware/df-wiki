<?php
# LocalSettings.php for Staging Wiki (migration target)
# Writable instance for testing the upload pipeline.

# Protect against web entry
if ( !defined( 'MEDIAWIKI' ) ) {
    exit;
}

## General settings
$wgSitename = "DreamFactory Wiki (Staging)";
$wgMetaNamespace = "DreamFactory_Wiki";

## Server and paths
$wgServer = WebRequest::detectServer();
$wgScriptPath = "";
$wgArticlePath = "/index.php/$1";

## Site logo — image is 300x300, Vector skin will scale via CSS
$wgLogo = '/images/5/55/Dreamfactoryicon.webp';

## Database settings
$wgDBtype = "mysql";
$wgDBserver = "staging-wiki-db";
$wgDBname = "staging_wiki";
$wgDBuser = "wiki_user";
$wgDBpassword = "wiki_pass";
$wgDBprefix = "";
$wgDBTableOptions = "ENGINE=InnoDB, DEFAULT CHARSET=binary";

## Shared memory / caching
$wgMainCacheType = CACHE_NONE;
$wgMemCachedServers = [];

## Security keys (local staging only — not used in production)
$wgSecretKey = "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3";
$wgUpgradeKey = "b2c3d4e5f6a1b2c3";

## File uploads — enabled for image migration
$wgEnableUploads = true;
$wgFileExtensions = array_merge(
    $wgFileExtensions,
    [ 'svg', 'webp' ]
);

## Skin
wfLoadSkin( 'Vector' );
$wgDefaultSkin = "vector";

## Extensions
wfLoadExtension( 'SyntaxHighlight_GeSHi' );
wfLoadExtension( 'MultimediaViewer' );
wfLoadExtension( 'ParserFunctions' );
$wgPFEnableStringFunctions = true;
wfLoadExtension( 'WikiSEO' );

## API — must be enabled for mwclient uploads
$wgEnableAPI = true;
$wgEnableWriteAPI = true;

## Language
$wgLanguageCode = "en";

## Custom namespaces for versioned documentation
define( "NS_V2", 3000 );
define( "NS_V2_TALK", 3001 );
define( "NS_V3", 3002 );
define( "NS_V3_TALK", 3003 );
define( "NS_V4", 3004 );
define( "NS_V4_TALK", 3005 );
define( "NS_V5", 3006 );
define( "NS_V5_TALK", 3007 );
define( "NS_V6", 3008 );
define( "NS_V6_TALK", 3009 );
define( "NS_LEGACY", 3010 );
define( "NS_LEGACY_TALK", 3011 );

$wgExtraNamespaces[NS_V2] = "V2";
$wgExtraNamespaces[NS_V2_TALK] = "V2_talk";
$wgExtraNamespaces[NS_V3] = "V3";
$wgExtraNamespaces[NS_V3_TALK] = "V3_talk";
$wgExtraNamespaces[NS_V4] = "V4";
$wgExtraNamespaces[NS_V4_TALK] = "V4_talk";
$wgExtraNamespaces[NS_V5] = "V5";
$wgExtraNamespaces[NS_V5_TALK] = "V5_talk";
$wgExtraNamespaces[NS_V6] = "V6";
$wgExtraNamespaces[NS_V6_TALK] = "V6_talk";
$wgExtraNamespaces[NS_LEGACY] = "Legacy";
$wgExtraNamespaces[NS_LEGACY_TALK] = "Legacy_talk";

## Disable rate limits for staging (allow rapid batch uploads)
$wgRateLimits['edit']['anon'] = [ 0, 60 ];
$wgRateLimits['edit']['bot'] = [ 0, 60 ];
$wgRateLimits['create']['anon'] = [ 0, 60 ];
$wgRateLimits['create']['bot'] = [ 0, 60 ];
$wgRateLimits['upload']['anon'] = [ 0, 60 ];
$wgRateLimits['upload']['bot'] = [ 0, 60 ];

## Allow bots to bypass some restrictions
$wgGroupPermissions['bot']['noratelimit'] = true;
$wgGroupPermissions['bot']['bot'] = true;
$wgGroupPermissions['sysop']['noratelimit'] = true;
$wgGroupPermissions['*']['noratelimit'] = true;
$wgGroupPermissions['*']['editinterface'] = true;
$wgGroupPermissions['*']['editsitecss'] = true;
$wgGroupPermissions['*']['editsitejs'] = true;

## Debug (staging only)
$wgShowExceptionDetails = true;
$wgShowDBErrorBacktrace = true;
