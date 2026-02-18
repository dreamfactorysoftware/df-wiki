<?php
# ============================================================
# PRODUCTION LocalSettings.php — wiki.dreamfactory.com
# All credentials MUST be supplied via environment variables.
# See .env.example for required variables.
# ============================================================

# Protect against web entry
if ( !defined( 'MEDIAWIKI' ) ) {
    exit;
}

## General settings
$wgSitename = "DreamFactory Wiki";
$wgMetaNamespace = "DreamFactory_Wiki";

## Server and paths — hardcoded to prevent host header injection
$wgServer = "https://wiki.dreamfactory.com";
$wgScriptPath = "";
$wgArticlePath = "/$1";

## Enable subpages in main namespace (required for old wiki redirects like DreamFactory/Installation)
$wgNamespacesWithSubpages[NS_MAIN] = true;

## Site logo — image is 300x300, Vector skin will scale via CSS
$wgLogo = '/images/5/55/Dreamfactoryicon.webp';
$wgFavicon = '/favicon.ico';

## Database settings — all credentials from environment
$wgDBtype = "mysql";
$wgDBserver = "wiki-db";
$wgDBname = getenv( 'MW_DB_NAME' ) ?: 'wiki_production';
$wgDBuser = getenv( 'MW_DB_USER' ) ?: 'wiki_user';
$wgDBpassword = getenv( 'MW_DB_PASSWORD' );
$wgDBprefix = "";
$wgDBTableOptions = "ENGINE=InnoDB, DEFAULT CHARSET=binary";

## Shared memory / caching
$wgMainCacheType = CACHE_NONE;
$wgMemCachedServers = [];

## Security keys — from environment, no defaults
$wgSecretKey = getenv( 'MW_SECRET_KEY' );
$wgUpgradeKey = getenv( 'MW_UPGRADE_KEY' );

## File uploads
$wgEnableUploads = true;
$wgFileExtensions = array_merge(
    $wgFileExtensions,
    [ 'webp' ]
);
# SVG disabled — XSS vector, not needed for documentation
$wgMaxUploadSize = 5 * 1024 * 1024; // 5 MB

## External content restrictions
$wgAllowExternalImages = false;
$wgRawHtml = false;

## Skin
wfLoadSkin( 'Vector' );
$wgDefaultSkin = "vector";

## Extensions
wfLoadExtension( 'SyntaxHighlight_GeSHi' );
wfLoadExtension( 'MultimediaViewer' );
wfLoadExtension( 'ParserFunctions' );
$wgPFEnableStringFunctions = true;
wfLoadExtension( 'WikiSEO' );

## API — enabled for bot uploads only
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

# ==============================================================
# Permissions — CI/CD-managed docs wiki, not community-editable
# ==============================================================

## Anonymous users — zero write permissions
$wgGroupPermissions['*']['edit'] = false;
$wgGroupPermissions['*']['createpage'] = false;
$wgGroupPermissions['*']['createtalk'] = false;
$wgGroupPermissions['*']['writeapi'] = false;
$wgGroupPermissions['*']['upload'] = false;
$wgGroupPermissions['*']['reupload'] = false;
$wgGroupPermissions['*']['createaccount'] = false;
$wgGroupPermissions['*']['editinterface'] = false;
$wgGroupPermissions['*']['editsitecss'] = false;
$wgGroupPermissions['*']['editsitejs'] = false;

## Regular users — read-only (account creation disabled above)
$wgGroupPermissions['user']['edit'] = false;
$wgGroupPermissions['user']['createpage'] = false;
$wgGroupPermissions['user']['createtalk'] = false;
$wgGroupPermissions['user']['upload'] = false;
$wgGroupPermissions['user']['reupload'] = false;
$wgGroupPermissions['user']['writeapi'] = false;

## Bot group — full write access for CI/CD deploys
$wgGroupPermissions['bot']['edit'] = true;
$wgGroupPermissions['bot']['createpage'] = true;
$wgGroupPermissions['bot']['createtalk'] = true;
$wgGroupPermissions['bot']['writeapi'] = true;
$wgGroupPermissions['bot']['upload'] = true;
$wgGroupPermissions['bot']['reupload'] = true;
$wgGroupPermissions['bot']['bot'] = true;
$wgGroupPermissions['bot']['noratelimit'] = true;
$wgGroupPermissions['bot']['editinterface'] = true;
$wgGroupPermissions['bot']['editsitecss'] = true;
$wgGroupPermissions['bot']['editsitejs'] = true;

## Sysop — full control
$wgGroupPermissions['sysop']['noratelimit'] = true;
$wgGroupPermissions['sysop']['editinterface'] = true;
$wgGroupPermissions['sysop']['editsitecss'] = true;
$wgGroupPermissions['sysop']['editsitejs'] = true;

## Rate limits for non-bot users
$wgRateLimits['edit']['user'] = [ 8, 60 ];
$wgRateLimits['create']['user'] = [ 4, 60 ];
$wgRateLimits['upload']['user'] = [ 4, 60 ];

# ==============================================================
# Security hardening
# ==============================================================

## Debug — fully disabled in production
$wgShowExceptionDetails = false;
$wgShowDBErrorBacktrace = false;
$wgShowSQLErrors = false;
$wgShowHostnames = false;

## Cookie security
$wgCookieSecure = true;
$wgCookieHttpOnly = true;
$wgCookieSameSite = 'Lax';

## Password policy — minimum 10 characters
$wgPasswordPolicy['policies']['default']['MinimalPasswordLength'] = [
    'value' => 10,
    'suggestChangeOnLogin' => true,
    'forceChange' => true,
];
