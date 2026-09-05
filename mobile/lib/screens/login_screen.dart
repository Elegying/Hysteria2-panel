import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../core/app_controller.dart';
import '../core/glass.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _address = TextEditingController();
  final _port = TextEditingController();
  final _username = TextEditingController();
  final _password = TextEditingController();
  bool _obscure = true;
  String? _error;

  @override
  void dispose() {
    _address.dispose();
    _port.dispose();
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _error = null);
    try {
      await ref
          .read(appControllerProvider.notifier)
          .login(
            address: _address.text,
            port: int.parse(_port.text),
            username: _username.text,
            password: _password.text,
          );
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final working = ref.watch(appControllerProvider).working;
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Form(
                key: _formKey,
                autovalidateMode: AutovalidateMode.onUserInteraction,
                child: AutofillGroup(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Align(
                        alignment: Alignment.centerLeft,
                        child: SvgPicture.asset(
                          'assets/h2-icon.svg',
                          width: 64,
                          height: 64,
                        ),
                      ),
                      const SizedBox(height: 24),
                      Text('Hysteria2管理', style: theme.textTheme.headlineLarge),
                      const SizedBox(height: 8),
                      Text(
                        '你的服务，尽在掌握。',
                        style: theme.textTheme.titleMedium?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                      const SizedBox(height: 28),
                      GlassCard(
                        child: Padding(
                          padding: const EdgeInsets.all(20),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Text('连接管理面板', style: theme.textTheme.titleLarge),
                              const SizedBox(height: 6),
                              Text(
                                '输入服务器地址与管理员账号',
                                style: theme.textTheme.bodySmall,
                              ),
                              const SizedBox(height: 22),
                              TextFormField(
                                controller: _address,
                                keyboardType: TextInputType.url,
                                autocorrect: false,
                                textInputAction: TextInputAction.next,
                                decoration: const InputDecoration(
                                  labelText: '面板地址',
                                  prefixIcon: Icon(Icons.language_rounded),
                                  helperText:
                                      '仅支持 HTTPS，例如 https://panel.example.com',
                                ),
                                validator: (value) =>
                                    value == null || value.trim().isEmpty
                                    ? '请输入面板地址'
                                    : null,
                              ),
                              const SizedBox(height: 14),
                              TextFormField(
                                controller: _port,
                                keyboardType: TextInputType.number,
                                textInputAction: TextInputAction.next,
                                inputFormatters: [
                                  FilteringTextInputFormatter.digitsOnly,
                                ],
                                validator: (value) {
                                  final port = int.tryParse(value ?? '');
                                  if (port == null ||
                                      port < 1 ||
                                      port > 65535) {
                                    return '请输入 1 至 65535 之间的端口';
                                  }
                                  return null;
                                },
                                decoration: const InputDecoration(
                                  labelText: '面板端口',
                                  prefixIcon: Icon(
                                    Icons.settings_ethernet_rounded,
                                  ),
                                ),
                              ),
                              const SizedBox(height: 14),
                              TextFormField(
                                controller: _username,
                                autofillHints: const [AutofillHints.username],
                                textInputAction: TextInputAction.next,
                                decoration: const InputDecoration(
                                  labelText: '面板账号',
                                  prefixIcon: Icon(
                                    Icons.person_outline_rounded,
                                  ),
                                ),
                                validator: (value) =>
                                    value == null || value.trim().isEmpty
                                    ? '请输入面板账号'
                                    : null,
                              ),
                              const SizedBox(height: 14),
                              TextFormField(
                                controller: _password,
                                obscureText: _obscure,
                                textInputAction: TextInputAction.done,
                                autofillHints: const [AutofillHints.password],
                                onFieldSubmitted: (_) =>
                                    working ? null : _login(),
                                decoration: InputDecoration(
                                  labelText: '面板密码',
                                  prefixIcon: const Icon(
                                    Icons.lock_outline_rounded,
                                  ),
                                  suffixIcon: IconButton(
                                    tooltip: _obscure ? '显示密码' : '隐藏密码',
                                    onPressed: () =>
                                        setState(() => _obscure = !_obscure),
                                    icon: Icon(
                                      _obscure
                                          ? Icons.visibility_outlined
                                          : Icons.visibility_off_outlined,
                                    ),
                                  ),
                                ),
                                validator: (value) =>
                                    value == null || value.isEmpty
                                    ? '请输入面板密码'
                                    : null,
                              ),
                              if (_error != null) ...[
                                Semantics(
                                  liveRegion: true,
                                  child: RefreshWarning(message: _error!),
                                ),
                                const SizedBox(height: 16),
                              ],
                              const SizedBox(height: 18),
                              FilledButton.icon(
                                onPressed: working ? null : _login,
                                icon: working
                                    ? const SizedBox.square(
                                        dimension: 18,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                        ),
                                      )
                                    : const Icon(Icons.arrow_forward_rounded),
                                label: Text(working ? '正在安全连接…' : '登录'),
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 20),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(
                            Icons.lock_outline_rounded,
                            size: 16,
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              '密码不会保存在本机，设备会话使用系统安全存储。',
                              style: theme.textTheme.bodySmall,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
