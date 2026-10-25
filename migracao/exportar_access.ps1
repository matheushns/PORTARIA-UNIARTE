# Exporta as tabelas do Access (.accdb) para JSON (UTF-8), para importar no novo sistema.
# Uso:  powershell -File migracao\exportar_access.ps1 -Origem "C:\caminho\arquivo.accdb"
param(
    [Parameter(Mandatory = $true)][string]$Origem,
    [string]$Destino = (Join-Path $PSScriptRoot "dados")
)
New-Item -ItemType Directory -Force -Path $Destino | Out-Null
$tmp = Join-Path $env:TEMP "bison_export.accdb"
Copy-Item -LiteralPath $Origem $tmp -Force

$conn = New-Object System.Data.OleDb.OleDbConnection("Provider=Microsoft.ACE.OLEDB.16.0;Data Source=$tmp")
$conn.Open()
foreach ($t in 'tbl_CadUsuarios', 'tblMoradores', 'tblVisitantes', 'tblEntregas') {
    $dt = New-Object System.Data.DataTable
    (New-Object System.Data.OleDb.OleDbDataAdapter("select * from [$t]", $conn)).Fill($dt) | Out-Null
    $rows = foreach ($r in $dt.Rows) {
        $o = [ordered]@{}
        foreach ($c in $dt.Columns) {
            $v = $r[$c.ColumnName]
            if ($v -is [System.DBNull]) { $v = $null }
            elseif ($v -is [datetime]) { $v = $v.ToString("yyyy-MM-dd HH:mm:ss") }
            elseif ($v -is [byte[]]) { $v = $null }   # anexos/imagens OLE ignorados
            $o[$c.ColumnName] = $v
        }
        $o
    }
    $json = ConvertTo-Json -InputObject @($rows) -Depth 4
    [System.IO.File]::WriteAllText((Join-Path $Destino "$t.json"), $json, (New-Object System.Text.UTF8Encoding($false)))
    "{0}: {1} registros" -f $t, $dt.Rows.Count
}
$conn.Close()
Remove-Item $tmp -Force
