/* Máscaras de digitação (sem dependências).
   Aplicadas automaticamente pelo atributo name dos campos:
   cpf*, telefone*/tel_residencial, placa*, rg*, bloco_apto e campos de nome (proprietario, *nome).
   Campos que já contêm texto livre (ex.: vários telefones) ficam sem máscara para não perder dados. */
(function () {
  const so = (v) => v.replace(/\D/g, '');

  const mascaras = {
    cpf(v) {
      const d = so(v).slice(0, 11);
      return d.replace(/^(\d{3})(\d)/, '$1.$2').replace(/^(\d{3})\.(\d{3})(\d)/, '$1.$2.$3')
              .replace(/^(\d{3})\.(\d{3})\.(\d{3})(\d)/, '$1.$2.$3-$4');
    },
    telefone(v) {
      const d = so(v).replace(/^0+/, '').slice(0, 11);
      if (d.length === 0) return '';
      if (d.length <= 2) return '(' + d;
      if (d.length <= 6) return '(' + d.slice(0, 2) + ') ' + d.slice(2);
      if (d.length <= 10) return '(' + d.slice(0, 2) + ') ' + d.slice(2, 6) + '-' + d.slice(6);
      return '(' + d.slice(0, 2) + ') ' + d.slice(2, 7) + '-' + d.slice(7);
    },
    placa(v) { return v.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 7); },
    rg(v) { return v.toUpperCase().replace(/[^0-9A-Z.\- ]/g, '').slice(0, 20); },
    apto(v) {
      const d = so(v).slice(0, 5);
      return d.length > 2 ? d.slice(0, 2) + '/' + d.slice(2) : d;
    },
    maiusculo(v) { return v.toUpperCase(); },
  };

  function tipo(nome) {
    if (/(^|_)cpf$/.test(nome) || /_cpf$/.test(nome)) return 'cpf';
    if (/(^|_)telefone$/.test(nome) || /(^|_)tel_residencial$/.test(nome)) return 'telefone';
    if (/(^|_)placa$/.test(nome)) return 'placa';
    if (/(^|_)rg$/.test(nome)) return 'rg';
    if (nome === 'bloco_apto') return 'apto';
    if (nome === 'proprietario' || /(^|_)nome$/.test(nome)) return 'maiusculo';
    return null;
  }

  function aplicar(input) {
    const t = tipo(input.name || '');
    if (!t || input.type === 'hidden') return;
    const fn = mascaras[t];
    if (input.value && (t === 'cpf' || t === 'telefone')) {
      const dig = t === 'telefone' ? so(input.value).replace(/^0+/, '') : so(input.value);
      if (/[A-Za-z]/.test(input.value) || dig.length > 11) return;
    }
    if (t === 'apto' && input.value && !/^\d{1,2}\/?\d*$/.test(input.value)) return;
    if (['cpf', 'telefone', 'apto'].includes(t)) input.inputMode = 'numeric';
    if (t === 'cpf') input.maxLength = 14;        // 000.000.000-00
    if (t === 'telefone') input.maxLength = 15;   // (00) 00000-0000
    if (t === 'maiusculo') {
      input.style.textTransform = 'uppercase';
      input.setAttribute('autocapitalize', 'characters');
    }
    input.autocomplete = 'off';
    input.placeholder = input.placeholder || { cpf: '000.000.000-00', telefone: '(00) 00000-0000',
      placa: 'ABC1D23', apto: '00/000', rg: '', maiusculo: '' }[t];
    input.value = fn(input.value);
    input.addEventListener('input', () => {
      const ini = input.selectionStart, fim = input.selectionEnd;
      const novo = fn(input.value);
      if (input.value !== novo) {
        input.value = novo;
        if (t === 'maiusculo' && ini !== null) input.setSelectionRange(ini, fim);
      }
    });
  }

  window.aplicarMascaras = (raiz) => raiz.querySelectorAll('input').forEach(aplicar);
  window.aplicarMascaras(document);
})();
