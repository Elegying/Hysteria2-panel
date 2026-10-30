package outbounds

import (
	"context"
	"net"
	"sync"
	"testing"

	"github.com/apernet/hysteria/extras/v2/adaptive"
)

func TestPanelAdaptiveOnlyChangesNewDefaultFlows(t *testing.T) {
	t.Setenv("HY2_ADAPTIVE_EGRESS_STATE_DIR", t.TempDir())
	oldUnsupported := adaptiveUnsupported.Swap(false)
	defer adaptiveUnsupported.Store(oldUnsupported)
	oldExit := adaptiveExit
	defer func() {
		if adaptiveExit != nil {
			adaptiveExit.Close()
		}
		adaptiveOnce = sync.Once{}
		adaptiveExit = oldExit
	}()
	adaptiveOnce = sync.Once{}
	adaptiveOnce.Do(func() {})
	adaptiveExit = adaptive.New("exit", "", func(context.Context) adaptive.Sample { return adaptive.Sample{IPv4: true} })
	original := &directOutbound{Mode: DirectOutboundModeAuto}
	degraded := original.adaptiveSnapshot()
	if degraded.Mode != DirectOutboundMode4 || original.Mode != DirectOutboundModeAuto {
		t.Fatal("mutated shared outbound")
	}
	for _, restricted := range []*directOutbound{
		{Mode: DirectOutboundMode6}, {Mode: DirectOutboundMode4},
		{Mode: DirectOutboundModeAuto, DeviceName: "other"},
		{Mode: DirectOutboundModeAuto, BindIP4: net.IPv4(192, 0, 2, 1)},
	} {
		if restricted.adaptiveSnapshot() != restricted {
			t.Fatal("overrode explicit routing")
		}
	}
	adaptiveExit.Close()
	adaptiveExit = adaptive.New("exit", "", func(context.Context) adaptive.Sample { return adaptive.Sample{IPv6: true} })
	if original.adaptiveSnapshot().Mode != DirectOutboundModeAuto || degraded.Mode != DirectOutboundMode4 {
		t.Fatal("recovery mutated existing flow")
	}
}

func TestPanelAdaptiveLiteralIPv6CannotBecomeIPv4(t *testing.T) {
	t.Setenv("HY2_ADAPTIVE_EGRESS_STATE_DIR", t.TempDir())
	oldUnsupported := adaptiveUnsupported.Swap(false)
	defer adaptiveUnsupported.Store(oldUnsupported)
	oldExit := adaptiveExit
	defer func() { adaptiveExit.Close(); adaptiveOnce = sync.Once{}; adaptiveExit = oldExit }()
	adaptiveOnce = sync.Once{}
	adaptiveOnce.Do(func() {})
	adaptiveExit = adaptive.New("exit", "", func(context.Context) adaptive.Sample { return adaptive.Sample{IPv4: true} })
	if addresses, err := adaptiveServerLookup("2001:db8::1"); err == nil || len(addresses) != 0 {
		t.Fatalf("invented IPv4: %v %v", addresses, err)
	}
	ips, err := adaptiveServerLookup("192.0.2.1")
	if err != nil || len(ips) != 1 || !ips[0].Equal(net.IPv4(192, 0, 2, 1)) {
		t.Fatal(ips, err)
	}
}

func TestPanelAdaptiveLocalDNSNamesNeverUsePublicFallback(t *testing.T) {
	for _, host := range []string{"printer", "printer.", "printer.local", "PRINTER.LOCAL.", "child.office.Local"} {
		if !adaptiveLocalName(host) {
			t.Fatalf("local name eligible for public fallback: %q", host)
		}
	}
	for _, host := range []string{"example.com", "example.com.", "notlocal.example", "local.example"} {
		if adaptiveLocalName(host) {
			t.Fatalf("public name classified local: %q", host)
		}
	}
}
