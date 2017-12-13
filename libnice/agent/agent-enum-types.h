


#ifndef __AGENT_ENUM_TYPES_H__
#define __AGENT_ENUM_TYPES_H__ 1

#include <glib-object.h>

G_BEGIN_DECLS
/* enumerations from "./agent.h" */
GType nice_component_state_get_type (void) G_GNUC_CONST;
#define NICE_TYPE_COMPONENT_STATE (nice_component_state_get_type())
GType nice_component_type_get_type (void) G_GNUC_CONST;
#define NICE_TYPE_COMPONENT_TYPE (nice_component_type_get_type())
GType nice_compatibility_get_type (void) G_GNUC_CONST;
#define NICE_TYPE_COMPATIBILITY (nice_compatibility_get_type())
GType nice_proxy_type_get_type (void) G_GNUC_CONST;
#define NICE_TYPE_PROXY_TYPE (nice_proxy_type_get_type())
GType nice_nomination_mode_get_type (void) G_GNUC_CONST;
#define NICE_TYPE_NOMINATION_MODE (nice_nomination_mode_get_type())
GType nice_agent_option_get_type (void) G_GNUC_CONST;
#define NICE_TYPE_AGENT_OPTION (nice_agent_option_get_type())
G_END_DECLS

#endif /* !AGENT_ENUM_TYPES_H */



