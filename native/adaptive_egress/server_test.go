package outbounds

import (
	"context"
	"fmt"
	"net"
	"sync"
	"testing"
	"time"

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
	adaptiveExit.Check(context.Background())
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
	adaptiveExit.Check(context.Background())
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
	adaptiveExit.Check(context.Background())
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

// Exercise the patched outbound entry points, not only the diagnosis helper.
// A blocked exit probe must never delay a new TCP/UDP flow or literal lookup.
func TestPanelAdaptiveEntryPointsDoNotWaitForProbe(t *testing.T) {
	for _, cached := range []bool{false, true} {
		for _, entry := range []string{"tcp", "udp", "dns"} {
			t.Run(fmt.Sprintf("%s/cached=%t", entry, cached), func(t *testing.T) {
				t.Setenv("HY2_ADAPTIVE_EGRESS_STATE_DIR", t.TempDir())
				oldUnsupported := adaptiveUnsupported.Swap(false)
				oldExit := adaptiveExit
				entered := make(chan struct{})
				stopped := make(chan struct{})
				var calls int
				adaptiveOnce = sync.Once{}
				adaptiveOnce.Do(func() {})
				controller := adaptive.New("entry-test", "", func(ctx context.Context) adaptive.Sample {
					calls++
					if cached && calls == 1 {
						return adaptive.Sample{IPv4: true}
					}
					close(entered)
					<-ctx.Done()
					close(stopped)
					return adaptive.Sample{}
				})
				adaptiveExit = controller
				defer func() {
					controller.Close()
					select {
					case <-stopped:
					case <-time.After(time.Second):
						t.Error("probe did not stop")
					}
					adaptiveExit = oldExit
					adaptiveOnce = sync.Once{}
					adaptiveUnsupported.Store(oldUnsupported)
				}()
				if cached {
					controller.Check(context.Background())
					controller.Invalidate()
				}
				// TCP reaches a real local listening socket; UDP writes to a real local
				// socket. Both exercise adaptiveSnapshot and the patched resolver path.
				listener, err := net.Listen("tcp4", "127.0.0.1:0")
				if err != nil {
					t.Fatal(err)
				}
				defer listener.Close()
				packet, err := net.ListenPacket("udp4", "127.0.0.1:0")
				if err != nil {
					t.Fatal(err)
				}
				defer packet.Close()
				direct := NewDirectOutboundSimple(DirectOutboundModeAuto)
				completed := make(chan error, 1)
				go func() {
					switch entry {
					case "tcp":
						conn, err := direct.TCP(&AddrEx{Host: "127.0.0.1", Port: uint16(listener.Addr().(*net.TCPAddr).Port)})
						if conn != nil {
							conn.Close()
						}
						completed <- err
					case "udp":
						addr := &AddrEx{Host: "127.0.0.1", Port: uint16(packet.LocalAddr().(*net.UDPAddr).Port)}
						conn, err := direct.UDP(addr)
						if err == nil {
							_, err = conn.WriteTo([]byte("probe-independent"), addr)
							conn.Close()
						}
						completed <- err
					case "dns":
						ips, err := adaptiveServerLookup("192.0.2.1")
						if err == nil && (len(ips) != 1 || !ips[0].Equal(net.IPv4(192, 0, 2, 1))) {
							err = fmt.Errorf("unexpected lookup: %v", ips)
						}
						completed <- err
					}
				}()
				select {
				case err := <-completed:
					if err != nil {
						t.Fatal(err)
					}
				case <-time.After(time.Second):
					t.Fatal("entry point waited for diagnosis")
				}
				select {
				case <-entered:
				case <-time.After(time.Second):
					t.Fatal("background probe did not start")
				}
				if cached && !controller.Snapshot().IPv4Only {
					t.Fatal("cached degradation lost")
				}
			})
		}
	}
}
