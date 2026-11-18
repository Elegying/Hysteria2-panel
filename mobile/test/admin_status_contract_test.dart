import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/screens/admin_controls.dart';

void main() {
  test(
    'TLS status consumes backend level, never assumes unknown means valid',
    () {
      expect(certificateLabel({'level': 'ok'}), '有效');
      expect(certificateLabel({'level': 'expired'}), '已过期');
      expect(certificateLabel({'level': 'not-yet-valid'}), '尚未生效');
      expect(certificateLabel({'level': 'unmonitored'}), '未配置监测');
      expect(certificateLabel({}), '状态未知');
    },
  );
}
