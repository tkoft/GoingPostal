


#include <config.h>
#include <glib-object.h>
#include "agent.h"
#include "agent-enum-types.h"

/* enumerations from "./agent.h" */
GType
nice_component_state_get_type (void)
{
  static GType type = 0;
  if (!type) {
    static const GEnumValue values[] = {
      { NICE_COMPONENT_STATE_DISCONNECTED, "NICE_COMPONENT_STATE_DISCONNECTED", "disconnected" },
      { NICE_COMPONENT_STATE_GATHERING, "NICE_COMPONENT_STATE_GATHERING", "gathering" },
      { NICE_COMPONENT_STATE_CONNECTING, "NICE_COMPONENT_STATE_CONNECTING", "connecting" },
      { NICE_COMPONENT_STATE_CONNECTED, "NICE_COMPONENT_STATE_CONNECTED", "connected" },
      { NICE_COMPONENT_STATE_READY, "NICE_COMPONENT_STATE_READY", "ready" },
      { NICE_COMPONENT_STATE_FAILED, "NICE_COMPONENT_STATE_FAILED", "failed" },
      { NICE_COMPONENT_STATE_LAST, "NICE_COMPONENT_STATE_LAST", "last" },
      { 0, NULL, NULL }
    };
    type = g_enum_register_static ("NiceComponentState", values);
  }
  return type;
}
GType
nice_component_type_get_type (void)
{
  static GType type = 0;
  if (!type) {
    static const GEnumValue values[] = {
      { NICE_COMPONENT_TYPE_RTP, "NICE_COMPONENT_TYPE_RTP", "rtp" },
      { NICE_COMPONENT_TYPE_RTCP, "NICE_COMPONENT_TYPE_RTCP", "rtcp" },
      { 0, NULL, NULL }
    };
    type = g_enum_register_static ("NiceComponentType", values);
  }
  return type;
}
GType
nice_compatibility_get_type (void)
{
  static GType type = 0;
  if (!type) {
    static const GEnumValue values[] = {
      { NICE_COMPATIBILITY_RFC5245, "NICE_COMPATIBILITY_RFC5245", "rfc5245" },
      { NICE_COMPATIBILITY_DRAFT19, "NICE_COMPATIBILITY_DRAFT19", "draft19" },
      { NICE_COMPATIBILITY_GOOGLE, "NICE_COMPATIBILITY_GOOGLE", "google" },
      { NICE_COMPATIBILITY_MSN, "NICE_COMPATIBILITY_MSN", "msn" },
      { NICE_COMPATIBILITY_WLM2009, "NICE_COMPATIBILITY_WLM2009", "wlm2009" },
      { NICE_COMPATIBILITY_OC2007, "NICE_COMPATIBILITY_OC2007", "oc2007" },
      { NICE_COMPATIBILITY_OC2007R2, "NICE_COMPATIBILITY_OC2007R2", "oc2007r2" },
      { NICE_COMPATIBILITY_LAST, "NICE_COMPATIBILITY_LAST", "last" },
      { 0, NULL, NULL }
    };
    type = g_enum_register_static ("NiceCompatibility", values);
  }
  return type;
}
GType
nice_proxy_type_get_type (void)
{
  static GType type = 0;
  if (!type) {
    static const GEnumValue values[] = {
      { NICE_PROXY_TYPE_NONE, "NICE_PROXY_TYPE_NONE", "none" },
      { NICE_PROXY_TYPE_SOCKS5, "NICE_PROXY_TYPE_SOCKS5", "socks5" },
      { NICE_PROXY_TYPE_HTTP, "NICE_PROXY_TYPE_HTTP", "http" },
      { NICE_PROXY_TYPE_LAST, "NICE_PROXY_TYPE_LAST", "last" },
      { 0, NULL, NULL }
    };
    type = g_enum_register_static ("NiceProxyType", values);
  }
  return type;
}
GType
nice_nomination_mode_get_type (void)
{
  static GType type = 0;
  if (!type) {
    static const GEnumValue values[] = {
      { NICE_NOMINATION_MODE_REGULAR, "NICE_NOMINATION_MODE_REGULAR", "regular" },
      { NICE_NOMINATION_MODE_AGGRESSIVE, "NICE_NOMINATION_MODE_AGGRESSIVE", "aggressive" },
      { 0, NULL, NULL }
    };
    type = g_enum_register_static ("NiceNominationMode", values);
  }
  return type;
}
GType
nice_agent_option_get_type (void)
{
  static GType type = 0;
  if (!type) {
    static const GFlagsValue values[] = {
      { NICE_AGENT_OPTION_REGULAR_NOMINATION, "NICE_AGENT_OPTION_REGULAR_NOMINATION", "regular-nomination" },
      { NICE_AGENT_OPTION_RELIABLE, "NICE_AGENT_OPTION_RELIABLE", "reliable" },
      { NICE_AGENT_OPTION_LITE_MODE, "NICE_AGENT_OPTION_LITE_MODE", "lite-mode" },
      { 0, NULL, NULL }
    };
    type = g_flags_register_static ("NiceAgentOption", values);
  }
  return type;
}



