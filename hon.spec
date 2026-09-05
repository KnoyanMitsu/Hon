Name:           hon
Version:        0.1.0
Release:        3%{?dist}
Summary:        Book reader manager built with GTK4 and libadwaita

License:        MIT
URL:            https://github.com/knoyan/hon
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       poppler-utils
Requires:       tesseract
Requires:       tesseract-langpack-eng
Requires:       tesseract-langpack-jpn
Requires:       tesseract-langpack-vie

%description
Hon adalah aplikasi manajemen dan pembaca buku (cbz/pdf)
dibangun dengan GTK4 dan libadwaita.

%prep
%setup -q

%build
# gak perlu compile, murni Python

%install
mkdir -p %{buildroot}/usr/share/hon
cp -r main.py window.py pages core %{buildroot}/usr/share/hon/

mkdir -p %{buildroot}/usr/bin
cat > %{buildroot}/usr/bin/hon <<'EOF'
#!/bin/bash
exec python3 /usr/share/hon/main.py "$@"
EOF
chmod +x %{buildroot}/usr/bin/hon

mkdir -p %{buildroot}/usr/share/applications
cp data/me.knoyan.Hon.desktop %{buildroot}/usr/share/applications/

mkdir -p %{buildroot}/usr/share/icons/hicolor/256x256/apps

%files
/usr/share/hon
/usr/bin/hon
/usr/share/applications/me.knoyan.Hon.desktop


%changelog
* Fri Sep 04 2026 Knoyan <you@example.com> - 0.1.0-1
- Initial release