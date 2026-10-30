package outbounds

import (
	"context"
	"net"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/apernet/hysteria/extras/v2/adaptive"
)

var adaptiveOnce sync.Once
var adaptiveExit *adaptive.Controller
var adaptiveUnsupported atomic.Bool

func registerAdaptiveOutbound(mode DirectOutboundMode, device string, ip4, ip6 net.IP) {
	if mode != DirectOutboundModeAuto || device != "" || ip4 != nil || ip6 != nil {
		adaptiveUnsupported.Store(true)
	}
}

// Enabled only by the managed service; explicit family policies remain intact.
func adaptiveServerState() adaptive.State {
	directory := os.Getenv("HY2_ADAPTIVE_EGRESS_STATE_DIR")
	if directory == "" || adaptiveUnsupported.Load() {
		return adaptive.State{}
	}
	adaptiveOnce.Do(func() {
		adaptiveExit = adaptive.New("server-default-exit-v1", directory, func(ctx context.Context) adaptive.Sample {
			d := &net.Dialer{Timeout: 4 * time.Second}
			return adaptive.Probe(ctx, func(ctx context.Context, address string) (net.Conn, error) { return d.DialContext(ctx, "tcp", address) }, func(ctx context.Context) (net.PacketConn, error) {
				var lc net.ListenConfig
				return lc.ListenPacket(ctx, "udp", ":0")
			})
		})
	})
	return adaptiveExit.Check(context.Background())
}

func adaptiveLocalName(host string) bool {
	host = strings.TrimSuffix(strings.ToLower(host), ".")
	return !strings.Contains(host, ".") || strings.HasSuffix(host, ".local")
}

func adaptiveServerLookup(host string) ([]net.IP, error) {
	state := adaptiveServerState()
	if !state.Verified || !state.IPv4Only {
		return net.LookupIP(host)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	// Preserve system IPv4 DNS (including local split DNS); only unreachable IPv6
	// resolver transports fall back to the managed public IPv4 resolver.
	resolver := &net.Resolver{PreferGo: true, Dial: func(ctx context.Context, network, address string) (net.Conn, error) {
		ip, _, err := net.SplitHostPort(address)
		if err != nil {
			return nil, err
		}
		if parsed := net.ParseIP(ip); parsed != nil && parsed.To4() == nil {
			if adaptiveLocalName(host) {
				return nil, &net.DNSError{Err: "IPv4 system resolver unavailable for local name", Name: host, IsTemporary: true}
			}
			address = "1.1.1.1:53"
		}
		d := &net.Dialer{Timeout: 3 * time.Second}
		return d.DialContext(ctx, network+"4", address)
	}}
	systemCtx, stopSystem := context.WithTimeout(ctx, 2*time.Second)
	ips, err := resolver.LookupIP(systemCtx, "ip4", host)
	stopSystem()
	if err == nil {
		return ips, nil
	}
	// Do not reinterpret NXDOMAIN or export local, single-label names.
	dnsErr, ok := err.(*net.DNSError)
	if !ok || dnsErr.IsNotFound || adaptiveLocalName(host) {
		return nil, err
	}
	fallback := &net.Resolver{PreferGo: true, Dial: func(ctx context.Context, network, _ string) (net.Conn, error) {
		d := &net.Dialer{Timeout: 2 * time.Second}
		return d.DialContext(ctx, network+"4", "1.1.1.1:53")
	}}
	return fallback.LookupIP(ctx, "ip4", host)
}

func (d *directOutbound) adaptiveSnapshot() *directOutbound {
	// The probe uses the default route, so never infer capability of a separately
	// bound interface or override an operator's explicit family restriction.
	if d.Mode != DirectOutboundModeAuto || d.DeviceName != "" || d.BindIP4 != nil || d.BindIP6 != nil {
		return d
	}
	state := adaptiveServerState()
	if !state.Verified || !state.IPv4Only {
		return d
	}
	copy := *d
	copy.Mode = DirectOutboundMode4
	return &copy
}
